import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Variante do gráfico 16: em vez do pico da execução INTEIRA (que às vezes
# vem de um SEGUNDO evento de escalonamento tardio, não do primeiro -- ex.:
# agg200 rep1 escalou em t=5s [pico 65%] e de novo em t=170s [pico 71.6%,
# o maior dos dois], então o "pico do run inteiro" nem sempre é "o pico que
# causou o primeiro SCALE_UP"), este gráfico usa só o pico ATÉ o primeiro
# SCALE_UP (inclusive) -- ou seja, a capacidade de 1 instância só, antes de
# qualquer ajuda extra. Para runs que nunca escalam, é o mesmo valor do
# gráfico 16 (o run inteiro já é só 1 instância).

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "graficos_apresentacao"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GREEN = "#1baf7a"
GRAY = "#888888"

AGGREGATE_TARGETS = [40, 100, 150, 200, 250, 300, 350, 400]


def is_fully_empty(summary_path):
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
raw_points = []  # (aggregate, pico_pre_escalonamento, escalou_em_algum_momento: bool)

for agg in AGGREGATE_TARGETS:
    metric_files = sorted(glob.glob(os.path.join(NB_DIR, f"metrics_normal_agg{agg}_WU10_refined_rep*.csv")))
    if not metric_files:
        print(f"[WARNING] Nenhum arquivo para agregado={agg}.")
        continue

    peaks, dropped = [], []
    for mf in metric_files:
        rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
        sf = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg{agg}_WU10_refined_rep{rep}.csv")
        if is_fully_empty(sf):
            dropped.append(rep)
            continue
        full_df = pd.read_csv(mf).iloc[1:]  # descarta t=0

        scale_up_idx = full_df.index[full_df["decision"] == "SCALE_UP"]
        escalou = len(scale_up_idx) > 0
        if escalou:
            # até a linha do primeiro SCALE_UP (inclusive) -- é essa leitura
            # que disparou a decisão, então é o "pico com 1 instância".
            first_scale_pos = full_df.index.get_loc(scale_up_idx[0])
            pre_scale_df = full_df.iloc[: first_scale_pos + 1]
        else:
            pre_scale_df = full_df

        peak = pre_scale_df["average_cpu_percent"].max()
        peaks.append(peak)
        raw_points.append((agg, peak, escalou))

    if dropped:
        print(f"[AVISO] agregado={agg}: repetição(ões) {dropped} totalmente vazia(s) excluída(s) (mesmo motivo das seções 43/54).")

    n_escalou = sum(1 for a, p, e in raw_points if a == agg and e)
    rows.append(dict(
        aggregate=agg, n=len(peaks),
        peak_mean=stats.mean(peaks),
        peak_std=stats.stdev(peaks) if len(peaks) > 1 else 0.0,
        peak_min=min(peaks), peak_max=max(peaks),
        n_escalou=n_escalou,
    ))

df = pd.DataFrame(rows)
print(df.to_string(index=False))

fig, ax = plt.subplots(figsize=(11, 7))

import random
random.seed(0)
for agg, peak, escalou in raw_points:
    jitter = agg * random.uniform(-0.02, 0.02)
    if escalou:
        ax.scatter(agg + jitter, peak, color=GREEN, marker="o", s=70, zorder=4,
                   edgecolors="white", linewidths=0.8)
    else:
        ax.scatter(agg + jitter, peak, facecolors="none", edgecolors=GRAY, marker="o",
                   s=70, zorder=4, linewidths=1.5)

ax.errorbar(df["aggregate"], df["peak_mean"], yerr=df["peak_std"],
            fmt="-", color=BLUE, linewidth=2, capsize=6, zorder=3,
            label="pico pré-escalonamento (média ± desvio)")
ax.fill_between(df["aggregate"], df["peak_min"], df["peak_max"], color=BLUE, alpha=0.06,
                 label="faixa min-max entre repetições", zorder=1)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=2)

from matplotlib.lines import Line2D
handles, labels = ax.get_legend_handles_labels()
handles += [
    Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=9,
           markeredgecolor="white", label="escalou em algum momento do run"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor=GRAY,
           markersize=9, markeredgewidth=1.5, label="nunca escalou"),
]
labels += ["escalou em algum momento do run", "nunca escalou"]

for _, row in df.iterrows():
    ax.annotate(f"{row['n_escalou']:.0f}/{row['n']:.0f} escalou",
                xy=(row["aggregate"], row["peak_max"]),
                xytext=(0, 10), textcoords="offset points",
                ha="center", fontsize=8.5, color="#333")

ax.set_xlabel("RPS agregado (tráfego normal, WU=10)")
ax.set_ylabel("CPU de pico -- só a janela com 1 instância (%)")
ax.set_title(
    "Capacidade de 1 instância só -- pico ANTES do primeiro escalonamento\n"
    "Mesmos dados do gráfico 16, mas cortando cada série no 1º SCALE_UP (ou no fim, se nunca escalou)"
)
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8.5)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "20_pico_pre_escalonamento_1_instancia.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
