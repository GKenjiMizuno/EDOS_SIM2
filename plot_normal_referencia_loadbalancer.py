import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Refaz o gráfico 24 no diretório dedicado graficos_apresentacao/04_pos_
# loadbalancer/, mesma regra dos demais desta leva (changes.txt §102-104).
#
# ATUALIZADO (changes.txt §140): a rep1 de normal_baseline agg40 refined
# (único arquivo deste gráfico) FOI recoletada no lote 1 (30/09, commit
# 712eb5a); o aviso antigo deste cabeçalho ("dado idêntico ao original, não
# recoletado") deixou de valer. A versão recoletada dá CPU ~3,8% (a antiga,
# de 20/08, ~7%). Resumo de tráfego: convenção "normal_" (mesma execução dos
# metrics_ atuais, §112), com fallback para o nome antigo. Versão com as 10
# reps e IC 95%: plot_normal_referencia_ic_loadbalancer.py (§135).

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer/01_capacidade_trafego_normal"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
INSTANCE_COLOR = "#555555"
REP = 1

path = os.path.join(NB_DIR, f"metrics_normal_agg40_WU10_refined_rep{REP}.csv")
df = pd.read_csv(path)

summary_path = os.path.join(NB_DIR, f"normal_traffic_summary_log_normal_agg40_WU10_refined_rep{REP}.csv")
if not os.path.exists(summary_path):
    summary_path = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg40_WU10_refined_rep{REP}.csv")
timeouts, ok, rate = 0, 0, 0.0
if os.path.exists(summary_path):
    sdf = pd.read_csv(summary_path)
    sdf = sdf[sdf["total_requests"].notna()]
    timeouts = int(sdf["errors"].sum())
    ok = int(sdf["total_requests"].sum())
    rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0

fig, ax = plt.subplots(figsize=(5.6, 5.2))

ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=BLUE, linewidth=1.8, zorder=3)
ax.axhline(60, color=BLUE, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)

ax2 = ax.twinx()
ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
          color=INSTANCE_COLOR, linewidth=1.3, linestyle="--", alpha=0.8, zorder=2)
ax2.set_ylim(0, 5)
ax2.set_yticks([1, 2, 3, 4])
ax2.set_ylabel("nº instâncias (tracejado)", fontsize=9, color=INSTANCE_COLOR)
ax2.tick_params(labelsize=8, colors=INSTANCE_COLOR)

ax.set_title(f"Tráfego normal isolado (rep{REP}) -- 40 agregado, WU=10\n{timeouts} timeouts ({rate:.1f}%) -- "
             "pós-correção (rep1 recoletada no lote 1)",
             fontsize=9.5)
ax.set_xlabel("tempo (s)", fontsize=9)
ax.set_ylabel("CPU média (%)", fontsize=9)
ax.set_ylim(0, 260)
ax.grid(True, alpha=0.2)
ax.tick_params(labelsize=8)

from matplotlib.lines import Line2D
legend_elems = [
    Line2D([0], [0], color=BLUE, lw=2, label="CPU média -- normal isolado (40 agregado, WU=10)"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.3, ls="--", label="nº de instâncias (eixo direito)"),
    Line2D([0], [0], color=BLUE, lw=0.8, ls=":", alpha=0.5, label="limiar SCALE_UP (60%)"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=1, fontsize=8, bbox_to_anchor=(0.5, 0.005))

fig.tight_layout(rect=[0, 0.14, 1, 1])
out_path = os.path.join(OUT_DIR, "24_normal_referencia_instancias_(loadbalancer).png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

