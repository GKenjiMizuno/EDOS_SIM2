"""
Gráfico-resumo consolidado das células furtivas CONFIRMADAS com 5 repetições
(changes.txt §156): junta §151 (edos_furtivo_wu_baixo, WU_normal=5000) e §155
(edos_furtivo_robusto). Mostra, por célula ordenada pela RAZÃO DE CUSTO
(WU_ataque/WU_normal), em quantas das 5 reps o ataque ficou furtivo-e-escalou
e em quantas escalou.

Mensagem: a furtividade robusta concentra-se em razão de custo ~2x (contraste
de RTT mínimo); razões maiores são frágeis/ruído.

Saída: .../03_deteccao_estatistica/07_furtivo_confirmado/resumo_furtivo_confirmado.png
"""
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

OUT_DIR = ("graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/"
           "07_furtivo_confirmado")
FURT, ESC, INK, MUTED, GRID = "#1baf7a", "#f59e0b", "#1f2937", "#6b7280", "#e5e7eb"

cells = []
# §151: WU_normal=5000, RPS=320
d1 = pd.read_csv("experiment_results/edos_furtivo_wu_baixo/confirma_5reps.csv")
for (wa, pct), g in d1.groupby(["wu_a", "pct"]):
    cells.append(dict(rps=320, wn=5000, wa=wa, pct=pct,
                      furt=int(g.furtivo.sum()), esc=int(g.escalou.sum()),
                      comb=g.comb.mean(), n=len(g), fonte="§151"))
# §155: parse "rps/WUnX/WUaY/Z%"
d2 = pd.read_csv("experiment_results/edos_furtivo_robusto/confirma_robusto_5reps.csv")
for cel, g in d2.groupby("cel"):
    m = re.match(r"(\d+)/WUn(\d+)/WUa(\d+)/(\d+)%", cel)
    rps, wn, wa, pct = map(int, m.groups())
    cells.append(dict(rps=rps, wn=wn, wa=wa, pct=pct,
                      furt=int(g.furtivo.sum()), esc=int(g.escalou.sum()),
                      comb=g.comb.mean(), n=len(g), fonte="§155"))

df = pd.DataFrame(cells)
df["razao"] = (df.wa / df.wn)
df = df.sort_values(["razao", "furt"], ascending=[True, False]).reset_index(drop=True)
df["rotulo"] = df.apply(lambda r: f"{r.rps} rps · WU_n {r.wn:,} · WU_a {r.wa:,} · {r.pct}%"
                        .replace(",", "."), axis=1)

fig, ax = plt.subplots(figsize=(12, 6))
y = np.arange(len(df))[::-1]  # razão menor em cima
ax.barh(y, df.furt, height=0.6, color=FURT, zorder=3, label="furtivo e escalou (de 5 reps)")
# marcador de "escalou" (confiabilidade de escalonamento)
ax.scatter(df.esc, y, marker="D", s=55, color=ESC, edgecolor="white", linewidth=0.8,
           zorder=4, label="escalou (de 5 reps)")
for yi, (_, r) in zip(y, df.iterrows()):
    ax.text(r.furt + 0.08, yi, f"{r.furt}/5", va="center", fontsize=9, color=FURT, fontweight="bold")
    ax.text(5.35, yi, f"razão {r.razao:.0f}×", va="center", fontsize=8.5, color=INK,
            fontweight="bold" if abs(r.razao - 2) < 0.1 else "normal")
    ax.text(6.25, yi, f"comb {r.comb:.1f}/11", va="center", fontsize=8, color=MUTED)

ax.set_yticks(y)
ax.set_yticklabels(df.rotulo, fontsize=9)
ax.set_xlim(0, 7.6)
ax.set_xticks(range(6))
ax.set_xlabel("Repetições (de 5)")
ax.grid(axis="x", color=GRID, zorder=0)
ax.set_axisbelow(True)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
ax.axvline(5, color=GRID, lw=1, zorder=1)
ax.set_title("Células furtivas confirmadas (5 repetições) — por razão de custo WU_ataque / WU_normal",
             fontsize=12.5, color=INK, pad=32)
ax.legend(handles=[Line2D([0], [0], color=FURT, lw=8, label="furtivo e escalou (barra)"),
                   Line2D([0], [0], marker="D", color="white", markerfacecolor=ESC, markersize=9,
                          label="escalou (losango)")],
          loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=2, fontsize=9, frameon=False)
fig.text(0.01, 0.01,
         "Furtivo = escalou no ataque E 0 das 11 janelas com alarme do combinado · 320/WU_n5000 = §151 · demais = §155 · "
         "baseline aparado [15,60) · detectores §143\n"
         "Leitura: a furtividade robusta concentra-se em razão de custo BAIXA (2–4×, contraste de RTT mínimo); cai a partir de 5× — o caso 20× é ruído de 1 rep.",
         fontsize=7.8, color=MUTED, va="bottom")
fig.subplots_adjust(left=0.3, right=0.97, top=0.85, bottom=0.15)
os.makedirs(OUT_DIR, exist_ok=True)
out = f"{OUT_DIR}/resumo_furtivo_confirmado.png"
fig.savefig(out, dpi=150)
plt.close(fig)
print("Salvo:", out)
print(df[["rotulo", "razao", "esc", "furt", "comb"]].to_string(index=False))
