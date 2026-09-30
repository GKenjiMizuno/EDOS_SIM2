import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

# Refaz o gráfico 55 com os dados de experiment_results/atacantes_intensidade_grid/
# já recoletados com a correção do load balancer (changes.txt §102-104). Não
# altera plot_atacantes_intensidade_heatmap_att4.py -- reimplementa a mesma
# lógica e salva no diretório dedicado graficos_apresentacao/04_pos_loadbalancer/.

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

NORMAL_SCENARIOS = {
    "S5": 20, "S1": 40, "S6": 80, "S2": 100,
    "S7": 160, "S3": 200, "S4": 300, "S8": 320,
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
        ))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

scenarios = list(NORMAL_SCENARIOS.keys())
mat = np.full((len(scenarios), len(INTENSITIES_PCT)), np.nan)
scaled = np.zeros((len(scenarios), len(INTENSITIES_PCT)), dtype=bool)
timeout_mat = np.full((len(scenarios), len(INTENSITIES_PCT)), np.nan)
for i, scenario in enumerate(scenarios):
    sub = grid[grid.scenario == scenario]
    for j, pct in enumerate(INTENSITIES_PCT):
        cell = sub[sub.pct == pct]
        if len(cell):
            mat[i, j] = cell["mean_cpu"].values[0]
            scaled[i, j] = bool(cell["escalou"].values[0])
            timeout_mat[i, j] = cell["timeout_pct"].values[0]

fig, ax = plt.subplots(figsize=(9, 7))
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
    "pós-correção do load balancer (changes.txt §102-104)",
    fontsize=11,
)

for i in range(len(scenarios)):
    for j in range(len(INTENSITIES_PCT)):
        if np.isnan(mat[i, j]):
            continue
        marca = " ▲" if scaled[i, j] else ""
        to = timeout_mat[i, j]
        to_str = f"\n{to:.0f}% to" if to and to > 0.5 else ""
        cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
        ax.text(j, i, f"{mat[i, j]:.0f}%{marca}{to_str}", ha="center", va="center",
                color=cor_texto, fontsize=9, fontweight="bold")

fig.colorbar(im, ax=ax, label="CPU média do run (%)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "55_atacantes_intensidade_heatmap_att4_media_(loadbalancer).png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
