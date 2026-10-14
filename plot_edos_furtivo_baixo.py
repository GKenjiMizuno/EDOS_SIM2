"""
Gráficos da bateria EDoS furtivo WU_ataque mínimo (changes.txt §150, dados §149):
320 rps, WU_normal=5000, WU_ataque {10000,20000,30000,40000} x intensidade
{5,10,15,20,30}% (+ 0%). Mapeia a fronteira de furtividade com contraste de RTT
mínimo. Reaproveita o desenho/detectores do plot_edos_furtivo_wu_rps (§148):
baseline aparado t∈[15,60), detectores recomendados (§143), rtt corrigido (§128).

Saídas em .../03_deteccao_estatistica/05_edos_furtivo_wu_baixo/: um painel por
célula + 1 heatmap (WU_ataque x intensidade) para Combinado e CUSUM lado a lado.
Uso: python3 plot_edos_furtivo_baixo.py [--heatmap-only]
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

D = "experiment_results/edos_furtivo_wu_baixo"
OUT_DIR = ("graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/"
           "05_edos_furtivo_wu_baixo")
RPS, WU_N = 320, 5000
WU_ATAQUE = [10000, 20000, 30000, 40000]
INTENS = [5, 10, 15, 20, 30]
ATK, INK = base.ATK, base.INK

# redireciona o módulo base para a pasta/saída desta bateria
base.D = D
base.OUT_DIR = OUT_DIR
os.makedirs(OUT_DIR, exist_ok=True)


def heatmap(df):
    atk = df[df.pct > 0]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    fig.subplots_adjust(left=0.07, right=0.88, top=0.84, bottom=0.14, wspace=0.25)
    im = None
    for ax, (col, nome) in zip(axes, [("comb", "Combinado (média + Z/CUSUM)"),
                                       ("cusum", "CUSUM 1000σ com reset")]):
        mat = np.full((len(WU_ATAQUE), len(INTENS)), np.nan)
        for i, wu_a in enumerate(WU_ATAQUE):
            for j, p in enumerate(INTENS):
                c = atk[(atk.wu_a == wu_a) & (atk.pct == p)]
                if len(c):
                    mat[i, j] = 100 * c[col].values[0] / c.n_jan.values[0]
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(INTENS)))
        ax.set_xticklabels([f"{p}%" for p in INTENS])
        ax.set_yticks(range(len(WU_ATAQUE)))
        ax.set_yticklabels([f"{wu:,}".replace(",", ".") for wu in WU_ATAQUE])
        ax.set_xlabel("Intensidade do ataque")
        ax.set_ylabel("WU do ataque (razão vs normal 5.000)")
        ax.set_title(nome, fontsize=11)
        for i, wu_a in enumerate(WU_ATAQUE):
            for j, p in enumerate(INTENS):
                c = atk[(atk.wu_a == wu_a) & (atk.pct == p)]
                if not len(c):
                    continue
                v = mat[i, j]
                esc = bool(c.escalou_atk.values[0])
                ax.text(j, i, f"{v:.0f}%\n{int(c[col].values[0])}/{int(c.n_jan.values[0])}",
                        ha="center", va="center", fontsize=8,
                        color="white" if v > 55 else INK, fontweight="bold")
                if esc and v == 0:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=ATK, lw=2.5, zorder=6))
                elif esc:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                               edgecolor="#f59e0b", lw=1.5, ls="--", zorder=5))
    cax = fig.add_axes([0.905, 0.2, 0.016, 0.55])
    fig.colorbar(im, cax=cax, label="% das 11 janelas do ataque com alarme")
    fig.legend(handles=[Patch(fc="none", ec=ATK, lw=2.5, label="escalou e 0 alarmes (FURTIVO)"),
                        Patch(fc="none", ec="#f59e0b", lw=1.5, ls="--", label="escalou (com algum alarme)")],
               loc="lower center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("EDoS furtivo com WU do ataque MÍNIMO — 320 rps, WU_normal=5.000\n"
                 "fronteira de contraste: WU_ataque x intensidade · baseline aparado · 1 rep", fontsize=12.5)
    out = f"{OUT_DIR}/heatmap_furtivo_wu_baixo.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("Salvo:", out)


if __name__ == "__main__":
    if "--heatmap-only" not in sys.argv:
        rows = []
        r0 = base.painel(RPS, WU_N, None, 0)
        if r0:
            rows.append(r0)
        for wu_a in WU_ATAQUE:
            for pct in INTENS:
                rr = base.painel(RPS, WU_N, wu_a, pct)
                if rr:
                    rows.append(rr)
                    flag = "  *** FURTIVO ***" if rr["furtivo"] else ""
                    print(f"awu{wu_a} atk{pct}%: escalou={rr['escalou_atk']} inst={rr['inst_max']} "
                          f"cpu={rr['cpu_pico']} base={rr['rtt_base_ms']}ms | "
                          f"comb {rr['comb']}/{rr['n_jan']} (cheio {rr['comb_base_cheio']}) "
                          f"cusum {rr['cusum']} z {rr['z']} ent {rr['ent']}{flag}")
        df = pd.DataFrame(rows)
        df.to_csv(f"{D}/resumo_edos_furtivo_wu_baixo.csv", index=False)
    else:
        df = pd.read_csv(f"{D}/resumo_edos_furtivo_wu_baixo.csv")
    heatmap(df)
