"""
Gráficos da bateria ROBUSTA de furtividade (changes.txt §154, dados §153):
grid consolidado RPS {160,320} x WU_normal {10,100,1000,10000} x WU_ataque
{10000,20000,50000,100000,200000} x intensidade {1,5,10,15,20,25}% (240 s,
ataque 60-180). Reaproveita painel/detectores de plot_edos_furtivo_wu_rps
(baseline aparado t∈[15,60), detectores §143, rtt corrigido §128).

Saídas em .../03_deteccao_estatistica/06_edos_furtivo_robusto/:
  - um painel por célula (236);
  - 2 heatmaps (Combinado e CUSUM), grade 2x4 de (RPS x WU_normal), cada um
    WU_ataque x intensidade, com moldura vermelha nas células FURTIVAS.
Uso: python3 plot_edos_furtivo_robusto.py [--heatmap-only]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

import plot_edos_furtivo_wu_rps as base

D = "experiment_results/edos_furtivo_robusto"
OUT_DIR = ("graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/"
           "06_edos_furtivo_robusto")
RPS_LIST = [160, 320]
WU_NORMAL = [10, 100, 1000, 10000]
WU_ATAQUE = [10000, 20000, 50000, 100000, 200000]
INTENS = [1, 5, 10, 15, 20, 25]
ATK, INK = base.ATK, base.INK

base.D = D
base.OUT_DIR = OUT_DIR
os.makedirs(OUT_DIR, exist_ok=True)


def heatmap(df, col, nome_det, arquivo):
    atk = df[df.pct > 0]
    fig, axes = plt.subplots(len(RPS_LIST), len(WU_NORMAL), figsize=(20, 9))
    fig.subplots_adjust(left=0.05, right=0.9, top=0.88, bottom=0.11, hspace=0.32, wspace=0.28)
    im = None
    for ri, rps in enumerate(RPS_LIST):
        for ci, wn in enumerate(WU_NORMAL):
            ax = axes[ri, ci]
            mat = np.full((len(WU_ATAQUE), len(INTENS)), np.nan)
            for i, wa in enumerate(WU_ATAQUE):
                for j, p in enumerate(INTENS):
                    c = atk[(atk.rps == rps) & (atk.wu_n == wn) & (atk.wu_a == wa) & (atk.pct == p)]
                    if len(c):
                        mat[i, j] = 100 * c[col].values[0] / c.n_jan.values[0]
            im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=100, aspect="auto")
            ax.set_xticks(range(len(INTENS)))
            ax.set_xticklabels([f"{p}%" for p in INTENS], fontsize=8)
            ax.set_yticks(range(len(WU_ATAQUE)))
            ax.set_yticklabels([f"{wa//1000}k" for wa in WU_ATAQUE], fontsize=8)
            ax.set_title(f"{rps} rps · WU_n={wn:,}".replace(",", "."), fontsize=10)
            if ri == len(RPS_LIST) - 1:
                ax.set_xlabel("Intensidade", fontsize=9)
            if ci == 0:
                ax.set_ylabel("WU do ataque", fontsize=9)
            for i, wa in enumerate(WU_ATAQUE):
                for j, p in enumerate(INTENS):
                    c = atk[(atk.rps == rps) & (atk.wu_n == wn) & (atk.wu_a == wa) & (atk.pct == p)]
                    if not len(c):
                        continue
                    v = mat[i, j]
                    esc = bool(c.escalou_atk.values[0])
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                            color="white" if v > 55 else INK, fontweight="bold")
                    if esc and v == 0:
                        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=ATK, lw=2.2, zorder=6))
                    elif esc:
                        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                                   edgecolor="#f59e0b", lw=1.3, ls="--", zorder=5))
    cax = fig.add_axes([0.915, 0.3, 0.012, 0.42])
    fig.colorbar(im, cax=cax, label="% das 11 janelas do ataque com alarme")
    fig.legend(handles=[Patch(fc="none", ec=ATK, lw=2.2, label="escalou e 0 alarmes (FURTIVO)"),
                        Patch(fc="none", ec="#f59e0b", lw=1.3, ls="--", label="escalou (com algum alarme)")],
               loc="lower center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle(f"Detecção do EDoS furtivo (bateria robusta) — {nome_det}\n"
                 "RPS x WU_normal x WU_ataque x intensidade · baseline aparado · 1 rep · valores = % das 11 janelas",
                 fontsize=13)
    out = f"{OUT_DIR}/{arquivo}"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("Salvo:", out)


if __name__ == "__main__":
    if "--heatmap-only" not in sys.argv:
        rows = []
        for rps in RPS_LIST:
            for wn in WU_NORMAL:
                r0 = base.painel(rps, wn, None, 0)
                if r0:
                    rows.append(r0)
                for wa in WU_ATAQUE:
                    if wa <= wn:
                        continue
                    for pct in INTENS:
                        rr = base.painel(rps, wn, wa, pct)
                        if rr:
                            rows.append(rr)
                            if rr["furtivo"]:
                                print(f"FURTIVO: agg{rps} nwu{wn} awu{wa} atk{pct}% "
                                      f"(cpu {rr['cpu_pico']}, comb {rr['comb']}/{rr['n_jan']})")
        df = pd.DataFrame(rows)
        df.to_csv(f"{D}/resumo_robusto.csv", index=False)
        print(f"\nTotal painéis: {len(rows)} | furtivas-e-escalaram: {int(df.furtivo.sum())}")
    else:
        df = pd.read_csv(f"{D}/resumo_robusto.csv")
    heatmap(df, "comb", "Combinado (média + Z/CUSUM)", "heatmap_robusto_combinado.png")
    heatmap(df, "cusum", "CUSUM 1000σ com reset", "heatmap_robusto_cusum.png")
