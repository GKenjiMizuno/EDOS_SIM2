import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

# Gráfico novo (não recriação -- ganha o próximo número livre da sequência,
# não segue o padrão "_(loadbalancer)"): mesmo desenho do gráfico 55
# (heatmap cenário x intensidade, só 4 atacantes), mas incluindo os 3
# cenários novos S9/S10/S11 (640/1280/2560 rps agregado normal, lote 2 da
# recoleta pós load balancer, ver changes.txt §109). Não altera
# plot_atacantes_intensidade_heatmap_att4_loadbalancer.py (gráfico 55).
#
# AVISO CRÍTICO descoberto ao investigar por que S9-S11 pareciam "não
# escalar direito": em S10/S11 (rps/cliente de tráfego normal = 320/640,
# acima do teto de ~200 rps/thread já documentado no gráfico 57), o
# tráfego normal E o de ataque rodam na MESMA thread/processo Python
# (main_orchestrator.py, GIL compartilhado) -- conforme a intensidade do
# ataque sobe, as threads de ataque brigam pelo GIL com as de tráfego
# normal, e o normal real entregue DESPENCA (ex.: S10 vai de 818 rps reais
# em 1% pra 36 rps reais em 25%, mesmo cenário, mesmo agregado nominal de
# 1280). Isso é MUITO mais severo que o simples "teto do gerador" visto no
# gráfico 57 -- lá o real ficava estável (~750-800) independente do
# nominal; aqui o real cai progressivamente conforme o ataque cresce, dentro
# do MESMO cenário. Anotado por célula (rps normal real vs nominal) e com
# borda de aviso quando o real cai abaixo de 50% do nominal.

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

NORMAL_SCENARIOS = {
    "S5": 20, "S1": 40, "S6": 80, "S2": 100,
    "S7": 160, "S3": 200, "S4": 300, "S8": 320,
    "S9": 640, "S10": 1280, "S11": 2560,
}
ATTACKERS = 4
INTENSITIES_PCT = [1, 5, 10, 15, 20, 25]
WORK_UNITS = 200000


def timeout_rate(suffix):
    af = os.path.join(GRID_DIR, f"attack_summary_log_{suffix}.csv")
    if not os.path.exists(af):
        return None
    adf = pd.read_csv(af)
    ok = pd.to_numeric(adf.get("total_requests"), errors="coerce").sum()
    errs = pd.to_numeric(adf.get("errors"), errors="coerce").sum()
    return 100.0 * errs / (ok + errs) if (ok + errs) > 0 else 0.0


def real_normal_rps(suffix):
    nf = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    if not os.path.exists(nf):
        return None
    ndf = pd.read_csv(nf)
    ndf = ndf[ndf["total_requests"].notna()]
    if not len(ndf):
        return None
    return ndf["real_rps"].sum()


rows = []
for scenario, agg in NORMAL_SCENARIOS.items():
    for pct in INTENSITIES_PCT:
        suffix = f"{scenario}_atk{pct}pct_att{ATTACKERS}_wu{WORK_UNITS}_rep1"
        mf = os.path.join(GRID_DIR, f"metrics_{suffix}.csv")
        if not os.path.exists(mf):
            print(f"[AVISO] faltando: {mf}")
            continue
        df = pd.read_csv(mf).iloc[1:]
        mean_cpu = df["average_cpu_percent"].mean()
        escalou = (df["decision"] == "SCALE_UP").any()
        rows.append(dict(
            scenario=scenario, agg=agg, pct=pct,
            mean_cpu=mean_cpu, escalou=escalou,
            timeout_pct=timeout_rate(suffix),
            real_normal=real_normal_rps(suffix),
        ))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

scenarios = list(NORMAL_SCENARIOS.keys())
mat = np.full((len(scenarios), len(INTENSITIES_PCT)), np.nan)
scaled = np.zeros((len(scenarios), len(INTENSITIES_PCT)), dtype=bool)
timeout_mat = np.full((len(scenarios), len(INTENSITIES_PCT)), np.nan)
real_mat = np.full((len(scenarios), len(INTENSITIES_PCT)), np.nan)
for i, scenario in enumerate(scenarios):
    sub = grid[grid.scenario == scenario]
    for j, pct in enumerate(INTENSITIES_PCT):
        cell = sub[sub.pct == pct]
        if len(cell):
            mat[i, j] = cell["mean_cpu"].values[0]
            scaled[i, j] = bool(cell["escalou"].values[0])
            timeout_mat[i, j] = cell["timeout_pct"].values[0]
            rn = cell["real_normal"].values[0]
            real_mat[i, j] = rn if rn is not None else np.nan

fig, ax = plt.subplots(figsize=(9, 9.5))
vmax = max(np.nanmax(mat), config.CPU_THRESHOLD_SCALE_UP)
im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")

ax.set_xticks(range(len(INTENSITIES_PCT)))
ax.set_xticklabels([f"{p}%" for p in INTENSITIES_PCT])
ax.set_yticks(range(len(scenarios)))
ax.set_yticklabels([f"{s} ({NORMAL_SCENARIOS[s]} rps)" for s in scenarios])
ax.set_xlabel("Intensidade do ataque (% do agregado normal)")
ax.set_ylabel("Cenário (rps agregado normal)")
ax.set_title(
    f"CPU média do run x cenário x intensidade -- só {ATTACKERS} atacantes "
    f"(WU={WORK_UNITS:,}, 1 rep)".replace(",", ".") + "\n"
    "▲ = SCALE_UP disparado -- \"to\" = % de timeout quando > 0.5% -- "
    "pós-correção do load balancer (changes.txt §102-104)\n"
    "S9-S11: \"real N%\" = tráfego normal REAL entregue / nominal -- abaixo de 50%, "
    "GIL do cliente disputado com o ataque (ver legenda)",
    fontsize=10.5,
)

for i in range(len(scenarios)):
    agg_nominal = NORMAL_SCENARIOS[scenarios[i]]
    for j in range(len(INTENSITIES_PCT)):
        if np.isnan(mat[i, j]):
            continue
        marca = " ▲" if scaled[i, j] else ""
        to = timeout_mat[i, j]
        to_str = f"\n{to:.0f}% to" if to and to > 0.5 else ""
        cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
        label = f"{mat[i, j]:.0f}%{marca}{to_str}"
        real = real_mat[i, j]
        grave = not np.isnan(real) and real < 0.5 * agg_nominal
        if not np.isnan(real) and real < 0.8 * agg_nominal:
            pct_real = 100.0 * real / agg_nominal
            label += f"\n(real {pct_real:.0f}%)"
        ax.text(j, i, label, ha="center", va="center",
                color=cor_texto, fontsize=8, fontweight="bold")
        if grave:
            rect = plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                  edgecolor="#d03b3b", linewidth=2.0, linestyle=":", zorder=6)
            ax.add_patch(rect)

from matplotlib.patches import Patch
legend_elems = [Patch(facecolor="none", edgecolor="#d03b3b", linewidth=2.0, linestyle=":",
                       label="borda vermelha tracejada = tráfego normal real < 50% do nominal\n"
                             "(GIL do cliente disputado entre tráfego normal e ataque -- não é "
                             "comportamento do servidor)")]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(0, -0.09), fontsize=7.5, frameon=False)

fig.colorbar(im, ax=ax, label="CPU média do run (%)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "58_atacantes_intensidade_heatmap_att4_extendido_S9_S11.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
