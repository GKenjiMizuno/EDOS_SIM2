import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Refaz o gráfico 20 com os dados de experiment_results/clients_rps_grid/ já
# recoletados com a correção do load balancer (changes.txt §102-104). Não
# altera plot_graph4_pico_pre_escalonamento.py -- reimplementa a mesma
# lógica (inclusive o filtro IQR, mantido por decisão explícita do usuário
# mesmo removendo sinal real perto do limiar -- ver script original) e salva
# no diretório dedicado graficos_apresentacao/04_pos_loadbalancer/.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

RED = "#d03b3b"
GRAY = "#888888"
CLIENT_COLORS = {
    1: "#2a78d6", 2: "#1baf7a", 4: "#e08a2b", 8: "#7a3fd6", 16: "#c2185b",
}

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]


def is_fully_empty(summary_path):
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
raw_points = []
removidos_reais = []

for agg in AGGREGATE_TARGETS:
    for clients in CLIENT_COUNTS:
        metric_files = sorted(glob.glob(
            os.path.join(GRID_DIR, f"metrics_agg{agg}_clients{clients}_WU10_rep*.csv")))
        if not metric_files:
            continue

        cell_peaks = []
        for mf in metric_files:
            rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
            full_df = pd.read_csv(mf).iloc[1:]

            scale_up_idx = full_df.index[full_df["decision"] == "SCALE_UP"]
            escalou = len(scale_up_idx) > 0
            if escalou:
                first_scale_pos = full_df.index.get_loc(scale_up_idx[0])
                pre_scale_df = full_df.iloc[: first_scale_pos + 1]
            else:
                pre_scale_df = full_df

            peak = pre_scale_df["average_cpu_percent"].max()
            cell_peaks.append((rep, peak, escalou))

        if len(cell_peaks) < 3:
            for rep, peak, escalou in cell_peaks:
                raw_points.append((agg, clients, peak, escalou, False))
            continue

        peaks_arr = np.array([p for _, p, _ in cell_peaks])
        q1, q3 = np.percentile(peaks_arr, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr

        kept_peaks = []
        for rep, peak, escalou in cell_peaks:
            is_outlier = peak < lo or peak > hi
            raw_points.append((agg, clients, peak, escalou, is_outlier))
            if is_outlier:
                if escalou:
                    removidos_reais.append((agg, clients, rep, peak))
                continue
            kept_peaks.append(peak)

        if not kept_peaks:
            continue

        n_escalou = sum(1 for r, p, e in cell_peaks if e and not (p < lo or p > hi))
        rows.append(dict(
            aggregate=agg, clients=clients, n=len(kept_peaks),
            peak_mean=stats.mean(kept_peaks),
            peak_std=stats.stdev(kept_peaks) if len(kept_peaks) > 1 else 0.0,
            n_escalou=n_escalou,
        ))

df = pd.DataFrame(rows)
print(df.to_string(index=False))
if removidos_reais:
    print("\n[AVISO] Pontos com SCALE_UP real removidos pelo filtro IQR (sinal, não ruído):")
    for agg, clients, rep, peak in removidos_reais:
        print(f"  agg={agg} clients={clients} rep={rep}: peak={peak:.1f}%")

fig, ax = plt.subplots(figsize=(12, 7.5))

import random
random.seed(0)
for agg, clients, peak, escalou, is_outlier in raw_points:
    if is_outlier:
        continue
    jitter = agg * random.uniform(-0.015, 0.015)
    color = CLIENT_COLORS[clients]
    if escalou:
        ax.scatter(agg + jitter, peak, color=color, marker="o", s=55, zorder=4,
                   edgecolors="white", linewidths=0.7)
    else:
        ax.scatter(agg + jitter, peak, facecolors="none", edgecolors=color, marker="o",
                   s=55, zorder=4, linewidths=1.3, alpha=0.6)

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("aggregate")
    if sub.empty:
        continue
    color = CLIENT_COLORS[clients]
    ax.errorbar(sub["aggregate"], sub["peak_mean"], yerr=sub["peak_std"],
                fmt="-", color=color, linewidth=1.8, capsize=4, zorder=3,
                label=f"{clients} cliente(s) -- média ± desvio")

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=2)

if removidos_reais:
    ax.text(0.98, 0.02,
            f"Nota: {len(removidos_reais)} execuções com SCALE_UP real foram removidas\n"
            f"pelo filtro IQR (zona-limite, agregado alto) -- ver console/changes.txt",
            transform=ax.transAxes, fontsize=7.5, va="bottom", ha="right",
            bbox=dict(boxstyle="round", facecolor="#fff3cd", edgecolor="#d6a100", alpha=0.9))

ax.set_xscale("log", base=2)
ax.set_xticks(AGGREGATE_TARGETS)
ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax.set_xlabel("RPS agregado alvo (escala log2)")
ax.set_ylabel("CPU de pico -- só a janela com 1 instância (%)")
ax.set_title(
    "Capacidade de 1 instância só -- pico ANTES do primeiro escalonamento\n"
    "Mesmos dados do gráfico 17 (grid RPS agregado × nº de clientes), outliers via IQR removidos -- "
    "pós-correção do load balancer (changes.txt §102-104)"
)
ax.legend(loc="upper left", fontsize=8, ncol=2)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "20_pico_pre_escalonamento_1_instancia_(loadbalancer).png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
