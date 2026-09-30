import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

# Gráficos 59/60/61 -- curva de capacidade do tráfego normal isolado, tudo de
# uma única sessão pós load balancer (run_normal_isolado_pos_lb.py, 1 rep por
# agregado, 20 -> 2560 rps). Três métricas por execução, uma por gráfico:
#   59 -- CPU média do run (sem t=0)
#   60 -- CPU de pico do run (sem t=0)
#   61 -- CPU de pico ANTES do primeiro SCALE_UP (inclusive), mesma definição
#         do gráfico 20; se o run nunca escala, é o pico do run inteiro.
# Cada ponto anota nº máximo de instâncias e o RPS real entregue (do
# normal_traffic_summary_log). Pontos onde o real ficou abaixo de 80% do
# nominal ganham anel vermelho: é o teto do gerador de tráfego do cliente
# (4 threads Python, changes.txt §112), não comportamento do servidor.

RESULTS_DIR = "experiment_results/normal_isolado_pos_lb"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [20, 40, 80, 160, 320, 640, 1280, 2560]
BLUE = "#2a78d6"
RED = "#d03b3b"
GRAY = "#888888"


def load_point(agg):
    suffix = f"agg{agg}_WU10_rep1"
    mf = os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")
    if not os.path.exists(mf):
        return None
    df = pd.read_csv(mf).iloc[1:]  # descarta t=0
    scale_idx = df.index[df["decision"] == "SCALE_UP"]
    if len(scale_idx):
        pre = df.iloc[: df.index.get_loc(scale_idx[0]) + 1]
    else:
        pre = df
    real = float("nan")
    nf = os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    if os.path.exists(nf):
        n = pd.read_csv(nf)
        n = n[n["total_requests"].notna()]
        if len(n):
            real = n["real_rps"].sum()
    return dict(
        agg=agg,
        mean_cpu=df["average_cpu_percent"].mean(),
        peak_cpu=df["average_cpu_percent"].max(),
        peak_pre=pre["average_cpu_percent"].max(),
        max_inst=int(df["num_instances"].max()),
        escalou=bool(len(scale_idx)),
        real_rps=real,
    )


rows = [p for p in (load_point(a) for a in AGGREGATE_TARGETS) if p is not None]
if not rows:
    raise SystemExit(f"Nenhum dado em {RESULTS_DIR}/ -- rode run_normal_isolado_pos_lb.py antes.")
data = pd.DataFrame(rows)
print(data.to_string(index=False))

GRAFICOS = [
    ("mean_cpu", "59_normal_isolado_cpu_media.png",
     "CPU média do run (%)", "CPU média -- tráfego normal isolado"),
    ("peak_cpu", "60_normal_isolado_cpu_pico.png",
     "CPU de pico do run (%)", "CPU de pico -- tráfego normal isolado"),
    ("peak_pre", "61_normal_isolado_pico_pre_escalonamento.png",
     "CPU de pico antes do 1º SCALE_UP (%)",
     "Pico pré-escalonamento (capacidade de 1 instância) -- tráfego normal isolado"),
]

for col, fname, ylabel, titulo in GRAFICOS:
    fig, ax = plt.subplots(figsize=(11, 6.5))
    x = data["agg"].values
    y = data[col].values
    ax.plot(x, y, "-", color=BLUE, linewidth=2, zorder=2)
    for _, r in data.iterrows():
        v = r[col]
        if r["escalou"]:
            ax.scatter(r["agg"], v, s=80, color=BLUE, edgecolors="white", linewidths=1, zorder=4)
        else:
            ax.scatter(r["agg"], v, s=80, facecolors="white", edgecolors=BLUE, linewidths=2, zorder=4)
        teto_cliente = not np.isnan(r["real_rps"]) and r["real_rps"] < 0.8 * r["agg"]
        if teto_cliente:
            ax.scatter(r["agg"], v, s=260, facecolors="none", edgecolors=RED,
                       linewidths=1.8, zorder=3)
        real_txt = f"real {r['real_rps']:.0f} rps" if not np.isnan(r["real_rps"]) else "real ?"
        ax.annotate(f"{v:.0f}%\n{r['max_inst']} inst.\n{real_txt}",
                    xy=(r["agg"], v), xytext=(0, 12), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8,
                    color=RED if teto_cliente else "#333333")

    ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color=RED, linestyle="--", linewidth=1,
               label=f"limiar SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)", zorder=1)
    ax.set_xscale("log", base=2)
    ax.set_xticks(AGGREGATE_TARGETS)
    ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
    ax.set_xlim(14, 3600)
    ax.set_ylim(0, max(100, np.nanmax(y) * 1.35))
    ax.set_xlabel("RPS agregado nominal (tráfego normal isolado, WU=10, 4 clientes, escala log2)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{titulo}\n1 execução por agregado, mesma sessão, pós-correção do load balancer",
                 fontsize=11.5)
    ax.grid(True, alpha=0.3)

    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color=RED, linestyle="--", linewidth=1,
               label=f"limiar SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=9,
               label="escalou (≥1 SCALE_UP)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor=BLUE, markeredgewidth=2, markersize=9, label="não escalou"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
               markeredgecolor=RED, markeredgewidth=1.8, markersize=14,
               label="teto do gerador do cliente (real < 80% do nominal)"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8.5)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, fname)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"Salvo: {out}")
