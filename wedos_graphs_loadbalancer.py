"""
Refaz o gráfico 6 (heatmap de pico de CPU, wedos_graphs.plot_heatmap) com os
dados de experiment_results/wedos_grid/ já recoletados com a correção do
load balancer (changes.txt §102-104). Não altera wedos_graphs.py -- reaproveita
carregar_grid() de lá (leitura de dados, sem lógica de plot) e reimplementa só
o heatmap, salvando num arquivo novo em vez de sobrescrever o original, para
poder comparar antes/depois lado a lado.

Padrão de nome combinado com o usuário: "<número>_(loadbalancer)" -- todo
gráfico pedido a partir de agora que precisar refletir dados pós-correção
segue esse sufixo, sem tocar no arquivo original correspondente.

Uso: python3 wedos_graphs_loadbalancer.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config
import wedos_graphs as wg

OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)


def plot_heatmap_loadbalancer(grid):
    grid = grid[grid["stage"] == "stage1a"]
    if grid.empty:
        print("[SKIP] heatmap (loadbalancer): sem dados de stage1a em wedos_grid/")
        return
    cenarios = sorted(grid["cenario"].unique())
    pcts = sorted(grid["pct"].unique())
    wus = sorted(grid["wu"].unique())

    fig, axes = plt.subplots(1, len(wus), figsize=(5.5 * len(wus), 5.8), squeeze=False)
    axes = axes[0]
    vmax = max(grid["peak_cpu"].max(), 60)
    for ax, wu in zip(axes, wus):
        mat = np.full((len(cenarios), len(pcts)), np.nan)
        scaled = np.zeros((len(cenarios), len(pcts)), dtype=bool)
        for i, sc in enumerate(cenarios):
            for j, pct in enumerate(pcts):
                sub = grid[(grid.cenario == sc) & (grid.pct == pct) & (grid.wu == wu)]
                if len(sub):
                    mat[i, j] = sub["peak_cpu"].mean()
                    scaled[i, j] = (sub["scaleups"] > 0).any()
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(pcts)))
        ax.set_xticklabels([f"{p:g}%" for p in pcts])
        ax.set_yticks(range(len(cenarios)))
        ax.set_yticklabels(cenarios)
        ax.set_xlabel("Intensidade do ataque")
        ax.set_title(f"WU = {wu:,}".replace(",", "."))
        for i in range(len(cenarios)):
            for j in range(len(pcts)):
                if np.isnan(mat[i, j]):
                    continue
                marca = " ▲" if scaled[i, j] else ""
                cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
                ax.text(j, i, f"{mat[i, j]:.0f}%{marca}", ha="center", va="center",
                        color=cor_texto, fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Cenário de tráfego normal (S1→S4 = volume crescente)")
    fig.suptitle("Pico de CPU por cenário × intensidade × custo (WU) — grade completa (Stage 1A)\n"
                  "▲ = pelo menos 1 SCALE_UP disparado nessa execução  —  "
                  "dados pós-correção do load balancer (changes.txt §102-104)",
                  fontsize=12, y=1.02)
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR, "06_wedos_heatmap_cpu_(loadbalancer).png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


if __name__ == "__main__":
    grid = wg.carregar_grid()
    print(f"Carregados {len(grid)} pontos de experiment_results/wedos_grid/ (pós-correção)\n")
    plot_heatmap_loadbalancer(grid)
