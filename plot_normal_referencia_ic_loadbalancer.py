import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import stats

# Gráfico 24 com intervalo de confiança (changes.txt §135), pedido do
# orientador. O 24 original (plot_normal_referencia_loadbalancer.py) mostra
# só a rep1; aqui entram as 10 repetições de normal_baseline agg40 refined
# (40 rps agregado, 4 clientes, WU=10): em cada instante, média das 10 reps
# e faixa do IC de 95% pela t de Student (média ± t(0,975; n-1)·s/√n).
# Resumo de tráfego: usa o arquivo com "normal_" no nome (mesma execução dos
# metrics_ atuais; convenção explicada no §112), com fallback para o antigo.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer/01_capacidade_trafego_normal"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
INSTANCE_COLOR = "#555555"
REPS = range(1, 11)


def resumo(rep):
    for nome in (f"normal_traffic_summary_log_normal_agg40_WU10_refined_rep{rep}.csv",
                 f"normal_traffic_summary_log_agg40_WU10_refined_rep{rep}.csv"):
        p = os.path.join(NB_DIR, nome)
        if os.path.exists(p):
            s = pd.read_csv(p)
            s = s[s["total_requests"].notna()]
            return int(s["total_requests"].sum()), int(s["errors"].sum())
    return 0, 0


def ic95(x):
    x = np.asarray(x, dtype=float)
    n = len(x)
    m = x.mean()
    h = stats.t.ppf(0.975, n - 1) * x.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return m, m - h, m + h


series, inst, cpu_run, req, err = [], [], [], 0, 0
for rep in REPS:
    df = pd.read_csv(os.path.join(NB_DIR, f"metrics_normal_agg40_WU10_refined_rep{rep}.csv"))
    df["t"] = (df["elapsed_time_s"] / 5).round() * 5  # grade de 5 s comum às 10 reps
    series.append(df.set_index("t")["average_cpu_percent"].rename(rep))
    inst.append(df.set_index("t")["num_instances"].rename(rep))
    cpu_run.append(df.loc[df["elapsed_time_s"] > 0, "average_cpu_percent"].mean())
    r, e = resumo(rep)
    req += r
    err += e

cpu = pd.concat(series, axis=1)
inst = pd.concat(inst, axis=1)
linhas = [ic95(cpu.loc[t].dropna()) for t in cpu.index]
media = np.array([l[0] for l in linhas])
lo = np.array([l[1] for l in linhas])
hi = np.array([l[2] for l in linhas])
m_run, lo_run, hi_run = ic95(cpu_run)
taxa_erro = 100.0 * err / req if req else 0.0

fig, ax = plt.subplots(figsize=(5.6, 5.4))
ax.fill_between(cpu.index, lo, hi, color=BLUE, alpha=0.25, lw=0, zorder=2)
ax.plot(cpu.index, media, color=BLUE, linewidth=1.8, zorder=3)
ax.axhline(60, color=BLUE, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)

# zoom: na escala 0-260% (a mesma dos painéis do 27) a faixa do IC some
zoom = ax.inset_axes([0.42, 0.50, 0.53, 0.36])
zoom.fill_between(cpu.index, lo, hi, color=BLUE, alpha=0.25, lw=0)
zoom.plot(cpu.index, media, color=BLUE, linewidth=1.4)
zoom.set_xlim(cpu.index.min(), cpu.index.max())
zoom.set_ylim(0, max(6, np.nanmax(hi) * 1.3))
zoom.set_title("zoom: CPU 0–6%", fontsize=7.5)
zoom.tick_params(labelsize=7)
zoom.grid(True, alpha=0.2)

ax2 = ax.twinx()
ax2.step(inst.index, inst.max(axis=1), where="post",
         color=INSTANCE_COLOR, linewidth=1.3, linestyle="--", alpha=0.8, zorder=2)
ax2.set_ylim(0, 5)
ax2.set_yticks([1, 2, 3, 4])
ax2.set_ylabel("nº instâncias (tracejado)", fontsize=9, color=INSTANCE_COLOR)
ax2.tick_params(labelsize=8, colors=INSTANCE_COLOR)

ax.set_title(f"Tráfego normal isolado -- 40 agregado, WU=10 -- média de {len(REPS)} repetições\n"
             f"CPU média do teste: {m_run:.1f}% (IC 95%: {lo_run:.1f}–{hi_run:.1f}%) · "
             f"{err} timeouts ({taxa_erro:.1f}%)".replace(".", ","),
             fontsize=9.5)
ax.set_xlabel("tempo (s)", fontsize=9)
ax.set_ylabel("CPU média (%)", fontsize=9)
ax.set_ylim(0, 260)
ax.grid(True, alpha=0.2)
ax.tick_params(labelsize=8)

legend_elems = [
    Line2D([0], [0], color=BLUE, lw=2, label=f"CPU média das {len(REPS)} repetições (40 agregado, WU=10)"),
    Patch(color=BLUE, alpha=0.25, label="intervalo de confiança de 95% (t de Student)"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.3, ls="--", label="nº de instâncias (máximo entre as reps; eixo direito)"),
    Line2D([0], [0], color=BLUE, lw=0.8, ls=":", alpha=0.5, label="limiar SCALE_UP (60%)"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=1, fontsize=8, bbox_to_anchor=(0.5, 0.005))

fig.tight_layout(rect=[0, 0.17, 1, 1])
out_path = os.path.join(OUT_DIR, "24_normal_referencia_instancias_ic_(loadbalancer).png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
print(f"CPU média por rep: {[round(c, 2) for c in cpu_run]}")
print(f"CPU média do teste: {m_run:.2f}% IC95 [{lo_run:.2f}, {hi_run:.2f}] | largura máx da faixa: {np.nanmax(hi - lo):.2f} pp")
