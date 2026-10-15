"""
Gráfico-resumo da confirmação das células furtivas (changes.txt §152, dados §151):
5 repetições de 4 células (320 rps, WU_normal=5000; WU_ataque x intensidade).
Lê experiment_results/edos_furtivo_wu_baixo/confirma_5reps.csv.

Painel (a): desfecho das 5 reps por célula (barras empilhadas) --
  furtivo-e-escalou / escalou mas detectado / não escalou.
Painel (b): alarmes do detector combinado por rep (de 11 janelas) -- mostra que
  o combinado fica em ~0 mesmo quando o ataque escala.

Saída: .../03_deteccao_estatistica/05_edos_furtivo_wu_baixo/resumo_confirma_furtivo.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

CSV = "experiment_results/edos_furtivo_wu_baixo/confirma_5reps.csv"
OUT_DIR = ("graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/"
           "05_edos_furtivo_wu_baixo")
WU_N = 5000
FURT, DET, NESC, INK, MUTED = "#1baf7a", "#f59e0b", "#9ca3af", "#1f2937", "#6b7280"

d = pd.read_csv(CSV)
celulas = [(10000, 15), (10000, 20), (10000, 30), (20000, 15)]
rotulos = [f"WU_ataque {wa:,}\n({wa // WU_N}×) · {p}%".replace(",", ".") for wa, p in celulas]

n_furt, n_detect, n_nesc = [], [], []
comb_por_rep = []
for wa, p in celulas:
    g = d[(d.wu_a == wa) & (d.pct == p)]
    furt = int((g.furtivo).sum())
    esc_det = int((g.escalou & ~g.furtivo).sum())
    nesc = int((~g.escalou).sum())
    n_furt.append(furt)
    n_detect.append(esc_det)
    n_nesc.append(nesc)
    comb_por_rep.append(g.sort_values("rep")[["rep", "comb", "escalou"]].values)

fig, (axa, axb) = plt.subplots(1, 2, figsize=(13.5, 5.6))
x = np.arange(len(celulas))

# (a) desfecho empilhado
axa.bar(x, n_furt, color=FURT, label="furtivo e escalou (0 alarme do combinado)")
axa.bar(x, n_detect, bottom=n_furt, color=DET, label="escalou mas foi detectado")
axa.bar(x, n_nesc, bottom=np.array(n_furt) + np.array(n_detect), color=NESC, label="não escalou")
for i in range(len(celulas)):
    if n_furt[i]:
        axa.text(i, n_furt[i] / 2, f"{n_furt[i]}", ha="center", va="center",
                 color="white", fontweight="bold", fontsize=11)
axa.set_xticks(x)
axa.set_xticklabels(rotulos, fontsize=8.5)
axa.set_ylim(0, 5.4)
axa.set_yticks(range(6))
axa.set_ylabel("Repetições (de 5)")
axa.set_title("(a) Desfecho das 5 repetições por célula", fontsize=11)
axa.grid(axis="y", alpha=0.2)
axa.set_axisbelow(True)
axa.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False)

# (b) alarmes do combinado por rep
for i, arr in enumerate(comb_por_rep):
    for rep, comb, esc in arr:
        cor = FURT if (esc and comb == 0) else (DET if esc else NESC)
        axb.scatter(i + (rep - 3) * 0.11, comb, s=60, color=cor, edgecolor="white",
                    linewidth=0.8, zorder=3)
axb.axhline(0, color=MUTED, lw=0.8, ls=":")
axb.set_xticks(x)
axb.set_xticklabels(rotulos, fontsize=8.5)
axb.set_ylim(-0.5, 11.5)
axb.set_ylabel("Janelas do ataque com alarme do combinado (de 11)")
axb.set_title("(b) Alarmes do combinado por repetição", fontsize=11)
axb.grid(axis="y", alpha=0.2)
axb.set_axisbelow(True)
axb.legend(handles=[Patch(color=FURT, label="furtivo e escalou"),
                    Patch(color=DET, label="escalou/detectado"),
                    Patch(color=NESC, label="não escalou")],
           fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False)

fig.suptitle("Confirmação do W-EDoS furtivo — 5 repetições por célula (320 rps, WU_normal=5.000, ataque WU>normal)",
             fontsize=12.5, color=INK)
fig.text(0.5, 0.005,
         "Furtivo = escalou no ataque E 0 das 11 janelas com alarme do combinado (média>1,8× E (Z OU CUSUM)) · "
         "baseline aparado t∈[15,60) · detectores §143 · dados: changes.txt §149-§151",
         ha="center", fontsize=7.6, color=MUTED)
fig.subplots_adjust(left=0.07, right=0.97, top=0.9, bottom=0.26, wspace=0.22)
os.makedirs(OUT_DIR, exist_ok=True)
out = f"{OUT_DIR}/resumo_confirma_furtivo.png"
fig.savefig(out, dpi=150)
plt.close(fig)
print("Salvo:", out)
print("\nResumo:")
for (wa, p), f, dt, ne in zip(celulas, n_furt, n_detect, n_nesc):
    print(f"  WU_a={wa} ({wa//WU_N}×) {p}%: furtivo-e-escalou {f}/5 · escalou-detectado {dt}/5 · não escalou {ne}/5")
