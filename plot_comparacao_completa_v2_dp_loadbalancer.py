import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# Gráfico 27 com desvio padrão (changes.txt §136), pedido do orientador.
# Mesmos painéis do plot_comparacao_completa_v2_loadbalancer.py (mesma rep
# representativa = a mais próxima da mediana de timeout das 5, mesma linha de
# instâncias); acrescenta, em cada painel, uma área semitransparente com
# média ± 1 desvio padrão da CPU entre as repetições daquele painel (5 reps
# nos painéis de ataque, 10 reps no painel normal agg40).
# Outliers: em cada instante (grade de 5 s), valores fora de
# [Q1 - 1,5·IQR, Q3 + 1,5·IQR] entre as reps são removidos antes de calcular
# média e DP (regra de Tukey). Pedido explícito do usuário/orientador; ver a
# ressalva do §68 (com 5 reps os quartis se apoiam em 1-2 valores).
# --com-outliers: mesma figura sem a remoção (para comparação).

COM_OUTLIERS = "--com-outliers" in sys.argv
DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer/02_caracterizacao_ataque"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
WU_COLOR = {100000: "#2a78d6", 200000: "#1baf7a", 400000: "#d03b3b"}
NORMAL_COLOR = "#7a3fd6"
INSTANCE_COLOR = "#555555"
NUM_REPS = 5
removidos_total, pontos_total = 0, 0


def timeout_info(summary_path):
    if not os.path.exists(summary_path):
        return 0, 0.0
    sdf = pd.read_csv(summary_path)
    sdf = sdf[sdf["total_requests"].notna()]
    timeouts = int(sdf["errors"].sum())
    ok = int(sdf["total_requests"].sum())
    rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0
    return timeouts, rate


def faixa_dp(paths):
    """média ± DP por instante entre as reps; remove outliers de Tukey salvo --com-outliers."""
    global removidos_total, pontos_total
    cols = []
    for k, p in enumerate(paths):
        d = pd.read_csv(p)
        d["t"] = (d["elapsed_time_s"] / 5).round() * 5
        cols.append(d.groupby("t")["average_cpu_percent"].mean().rename(k))
    m = pd.concat(cols, axis=1).sort_index()  # grades de 5 s podem diferir entre reps
    if not COM_OUTLIERS:
        q1, q3 = m.quantile(0.25, axis=1), m.quantile(0.75, axis=1)
        iqr = q3 - q1
        fora = m.lt(q1 - 1.5 * iqr, axis=0) | m.gt(q3 + 1.5 * iqr, axis=0)
        removidos_total += int(fora.values.sum())
        m = m.mask(fora)
    pontos_total += int(m.notna().values.sum() + (0 if COM_OUTLIERS else fora.values.sum()))
    return m.index.values, m.mean(axis=1).values, m.std(axis=1, ddof=1).values


def plot_single(ax, ax2, df, color, faixa, has_attack_window=True):
    if has_attack_window:
        attack_rows = df[df["label"] == "attack"]
        if not attack_rows.empty:
            ax.axvspan(attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max(),
                       color="#d03b3b", alpha=0.06, zorder=0)
    t, med, dp = faixa
    ax.fill_between(t, med - dp, med + dp, color=color, alpha=0.22, lw=0, zorder=2)
    ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=color, linewidth=1.6, zorder=3)
    ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
             color=INSTANCE_COLOR, linewidth=1.1, linestyle="--", alpha=0.8, zorder=2)


def finish_panel(ax, ax2, color, title, ylabel=None):
    ax.axhline(60, color=color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)
    ax2.set_ylim(0, 5)
    ax2.set_yticks([1, 2, 3, 4])
    ax2.tick_params(labelsize=7, colors=INSTANCE_COLOR)
    ax.set_ylim(0, 260)
    ax.set_title(title, fontsize=8.5)
    ax.grid(True, alpha=0.2)
    ax.tick_params(labelsize=7)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8)


fig = plt.figure(figsize=(15, 27))
gs = GridSpec(7, 3, figure=fig, height_ratios=[0.7] + [1] * 6, hspace=0.55, wspace=0.35)

# painel normal: mesma rep1 do 27 + faixa das 10 reps (resumo da mesma execução: convenção "normal_", §112)
ax_normal = fig.add_subplot(gs[0, 1])
df_normal = pd.read_csv(os.path.join(NB_DIR, "metrics_normal_agg40_WU10_refined_rep1.csv"))
t_n, r_n = timeout_info(os.path.join(NB_DIR, "normal_traffic_summary_log_normal_agg40_WU10_refined_rep1.csv"))
faixa_n = faixa_dp([os.path.join(NB_DIR, f"metrics_normal_agg40_WU10_refined_rep{r}.csv") for r in range(1, 11)])
ax2_normal = ax_normal.twinx()
plot_single(ax_normal, ax2_normal, df_normal, NORMAL_COLOR, faixa_n, has_attack_window=False)
finish_panel(ax_normal, ax2_normal, NORMAL_COLOR,
             f"NORMAL isolado (referência) -- 40 agregado, WU=10\n{t_n} timeouts ({r_n:.1f}%) -- rep1; "
             "faixa = 10 reps", ylabel="CPU média (%)")
fig.add_subplot(gs[0, 0]).axis("off")
fig.add_subplot(gs[0, 2]).axis("off")

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        color = WU_COLOR[wu]
        for row, condicao_label, condicao_dir in [(1 + i * 2, "COMBINADO", "combinado"),
                                                    (2 + i * 2, "ISOLADO", "isolado")]:
            ax = fig.add_subplot(gs[row, j])
            ax2 = ax.twinx()
            rates = []
            for rep in range(1, NUM_REPS + 1):
                _, rate = timeout_info(os.path.join(
                    DESEMPATE_DIR, f"attack_summary_log_{condicao_dir}_rps{rps}_att4_WU{wu}_rep{rep}.csv"))
                rates.append(rate)
            mediana = pd.Series(rates).median()
            rep_escolhida = min(range(1, NUM_REPS + 1), key=lambda r: abs(rates[r - 1] - mediana))
            paths = [os.path.join(DESEMPATE_DIR, f"metrics_{condicao_dir}_rps{rps}_att4_WU{wu}_rep{r}.csv")
                     for r in range(1, NUM_REPS + 1)]
            df_rep = pd.read_csv(paths[rep_escolhida - 1])
            plot_single(ax, ax2, df_rep, color, faixa_dp(paths))
            rate_txt = f"{sum(rates)/len(rates):.1f}%±{pd.Series(rates).std():.1f} (n=5)"
            title = (f"{condicao_label} -- rps={rps}, WU={wu:,}".replace(",", ".") +
                     f"\n{rate_txt} timeout -- rep{rep_escolhida} (mediana) -- pós-correção")
            finish_panel(ax, ax2, color, title, ylabel="CPU média (%)" if j == 0 else None)
            if row == 6:
                ax.set_xlabel("tempo (s)", fontsize=8)

regra = ("sem remoção de outliers" if COM_OUTLIERS else
         f"outliers removidos por quartis (fora de Q1−1,5·IQR, Q3+1,5·IQR em cada instante): "
         f"{removidos_total} de {pontos_total} pontos")
legend_elems = [
    Line2D([0], [0], color=WU_COLOR[100000], lw=2, label="CPU média -- WU=100.000 (rep representativa)"),
    Line2D([0], [0], color=WU_COLOR[200000], lw=2, label="CPU média -- WU=200.000 (rep representativa)"),
    Line2D([0], [0], color=WU_COLOR[400000], lw=2, label="CPU média -- WU=400.000 (rep representativa)"),
    Line2D([0], [0], color=NORMAL_COLOR, lw=2, label="CPU média -- normal isolado (referência)"),
    Patch(color="#888888", alpha=0.3, label="área = média ± 1 desvio padrão entre as repetições"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.1, ls="--", label="nº de instâncias (eixo direito)"),
    Line2D([0], [0], color="#888", lw=0.8, ls=":", label="limiar SCALE_UP (60%)"),
    Line2D([0], [0], color="#d03b3b", lw=6, alpha=0.15, label="janela de ataque"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 0.002))

fig.suptitle(
    "Comparação completa v2 -- PÓS-CORREÇÃO do load balancer, com desvio padrão entre repetições\n"
    "Linha: rep mais próxima da mediana de timeout das 5 (normal: agg40 rep1) · área: média ± 1 DP "
    "(5 reps; normal: 10 reps)\n" + regra,
    fontsize=12.5,
)
fig.tight_layout(rect=[0, 0.035, 1, 0.955])
nome = "27_comparacao_completa_v2_dp_com_outliers_(loadbalancer).png" if COM_OUTLIERS else \
    "27_comparacao_completa_v2_dp_(loadbalancer).png"
out_path = os.path.join(OUT_DIR, nome)
fig.savefig(out_path, dpi=105)
plt.close(fig)
print(f"Salvo: {out_path}")
print(regra)
