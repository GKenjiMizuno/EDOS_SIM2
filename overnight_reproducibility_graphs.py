import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Script temporario (nao roda simulacoes). Gera graficos sobre o achado de
# reprodutibilidade desta madrugada: curva de capacidade do baseline normal
# (WU=10) com os pontos repetidos (candidatos a S4), e um resumo do estado
# atual de wu_calibration.

NB = "experiment_results/normal_baseline"
WC = "experiment_results/wu_calibration"
OUT_DIR = "graficos_apresentacao"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GREEN = "#1baf7a"


def summarize(path):
    df = pd.read_csv(path)
    return df['average_cpu_percent'].max(), df['average_cpu_percent'].mean()


# ---------- Grafico 1: curva de capacidade (WU=10) ----------
points = []  # (agg_rps, peak_cpu, avg_cpu, is_repeated, label)
for f in sorted(glob.glob(os.path.join(NB, "metrics_normal_rps*_WU10.csv"))):
    name = os.path.basename(f)
    if "rep" in name:
        continue
    m = re.match(r"metrics_normal_rps([\d.]+)_WU10\.csv", name)
    if not m:
        continue
    rps = float(m.group(1))
    agg = rps * 4
    peak, avg = summarize(f)
    points.append((agg, peak, avg, False, name))

rep_paths = sorted(glob.glob(os.path.join(NB, "metrics_normal_rps62.5_WU10_rep*.csv")))
rep_peaks = []
for f in rep_paths:
    peak, avg = summarize(f)
    rep_peaks.append(peak)
    points.append((250, peak, avg, True, os.path.basename(f)))

points.sort(key=lambda p: p[0])

fig, ax = plt.subplots(figsize=(10, 6))
single_x = [p[0] for p in points if not p[3]]
single_y = [p[1] for p in points if not p[3]]
rep_x = [p[0] for p in points if p[3]]
rep_y = [p[1] for p in points if p[3]]

ax.plot(single_x, single_y, color=BLUE, marker='o', markersize=7, linewidth=1.5,
        label='CPU de pico (1 amostra)')
ax.scatter(rep_x, rep_y, color=RED, s=90, marker='X', zorder=5,
           label=f'CPU de pico (250 agregado, {len(rep_peaks)} repetições)')
ax.scatter([300], [87.9], color='orange', s=120, marker='D', zorder=5,
           label='300 agregado, reexecução (87.9% -- 1ª amostra: 53.6%)')
ax.axhline(60, color=RED, linestyle='--', linewidth=1, alpha=0.7, label='limiar SCALE_UP (60%)')

ax.set_xlabel('RPS agregado (tráfego normal, WU=10)')
ax.set_ylabel('CPU de pico (%)')
ax.set_title('Curva de capacidade do baseline normal (WU=10)\n'
              'Pontos com múltiplas amostras mostram a variância real entre execuções')
ax.legend(fontsize=9, loc='upper left')
ax.grid(True, alpha=0.3)
fig.tight_layout()
path1 = os.path.join(OUT_DIR, "04_curva_capacidade_reproducibilidade.png")
fig.savefig(path1, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"[OK] {path1}")


# ---------- Grafico 2: resumo wu_calibration atual ----------
rows = []
for f in sorted(glob.glob(os.path.join(WC, "metrics_rps*_att4_WU*.csv"))):
    name = os.path.basename(f)
    m = re.match(r"metrics_rps(\d+)_att4_WU(\d+)\.csv", name)
    rps, wu = int(m.group(1)), int(m.group(2))
    peak, avg = summarize(f)
    xlsx = os.path.join(WC, f"rtt_bursts_rps{rps}_att4_WU{wu}.xlsx")
    bursts = 0
    if os.path.exists(xlsx):
        bdf = pd.read_excel(xlsx)
        bursts = int((bdf['Status Burst'] == 'DDoS Burst').sum())
    asum = os.path.join(WC, f"attack_summary_log_{rps}_4_WU{wu}.csv")
    errs = 0
    if os.path.exists(asum):
        adf = pd.read_csv(asum)
        errs = int(pd.to_numeric(adf['errors'], errors='coerce').sum())
    rows.append(dict(rps=rps, wu=wu, peak_cpu=peak, bursts=bursts, errors=errs))

df = pd.DataFrame(rows)
rps_vals = sorted(df['rps'].unique())
wu_vals = sorted(df['wu'].unique())

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
width = 0.25
x = range(len(rps_vals))
colors = [BLUE, GREEN, RED]
for i, wu in enumerate(wu_vals):
    sub = df[df.wu == wu].set_index('rps').reindex(rps_vals)
    axes[0].bar([xi + (i - 1) * width for xi in x], sub['peak_cpu'], width=width,
                label=f'WU={wu:,}'.replace(",", "."), color=colors[i % 3])
    axes[1].bar([xi + (i - 1) * width for xi in x], sub['errors'], width=width,
                label=f'WU={wu:,}'.replace(",", "."), color=colors[i % 3])
axes[0].axhline(60, color=RED, linestyle='--', linewidth=1, alpha=0.6)
axes[0].set_xticks(list(x)); axes[0].set_xticklabels([f'rps={r}' for r in rps_vals])
axes[0].set_ylabel('CPU de pico (%)')
axes[0].set_title('wu_calibration (pós-fix) — CPU de pico')
axes[0].legend(fontsize=8)
axes[0].grid(True, axis='y', alpha=0.3)

axes[1].set_xticks(list(x)); axes[1].set_xticklabels([f'rps={r}' for r in rps_vals])
axes[1].set_ylabel('Total de erros de requisição')
axes[1].set_title('wu_calibration (pós-fix) — falhas de requisição')
axes[1].legend(fontsize=8)
axes[1].grid(True, axis='y', alpha=0.3)

fig.suptitle('Estado atual da varredura de calibração de WU (regenerada após os 3 fixes)', fontsize=12)
fig.tight_layout()
path2 = os.path.join(OUT_DIR, "05_wu_calibration_resumo_atual.png")
fig.savefig(path2, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"[OK] {path2}")
