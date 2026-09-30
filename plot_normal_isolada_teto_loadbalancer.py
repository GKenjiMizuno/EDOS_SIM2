import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

# Gráfico novo (não é recriação de um gráfico existente -- não segue o
# padrão "_(loadbalancer)" de sufixo, ganha o próximo número livre da
# sequência do projeto). Pedido do usuário: já que o load balancer mudou
# a carga real por instância, o teto de capacidade medido antes (~205-210
# req/s agregado, WU=10, ver wedos_repro_test.py/sweep fino) pode ter
# mudado -- procurar esse novo teto usando os dados de tráfego normal
# ISOLADO já existentes (normal_baseline/, família "pow2 base 20" usada
# nos gráficos 23/42), no mesmo estilo visual do gráfico 17 (heatmap
# anotado, célula = CPU, ▲ = escalou).
#
# Diferença de eixos em relação ao 17: aquele grid tinha uma segunda
# dimensão real (nº de clientes, decompondo o mesmo agregado). Este
# dataset não varia nº de clientes (sempre HTTP_NORMAL_NUM_CLIENTS=4) --
# a segunda dimensão aqui é REPETIÇÃO (1..10), o que serve igual de
# checagem visual: se o teto for real, a coluna inteira daquela linha
# deveria ficar consistentemente quente.
#
# Cobertura: até o §115 este gráfico marcava cada célula como pós-correção
# (borda verde) ou original não-recoletada, porque a recoleta de 802 só
# pegou quem tinha escalado. Depois do lote 1 (§115) todas as reps estão
# pós-correção -- marcação removida (§116).

NB_DIR = "experiment_results/normal_baseline"
PRE_DIR = "experiment_results/_pre_loadbalancer_fix/normal_baseline"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [20, 40, 80, 160, 320, 640, 1280, 2560]
MAX_REPS = 10
# 1280/2560 vêm de run_normal_isolado_s9_s11.py (lote 3 da recoleta pós
# load balancer, ver changes.txt §109) -- só 5 reps cada (não 10 como os
# agregados mais antigos), então as colunas rep6-rep10 dessas 2 linhas
# ficam em branco no heatmap, por design (sem dado, não erro).


def is_fully_empty(summary_path):
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
for agg in AGGREGATE_TARGETS:
    for rep in range(1, MAX_REPS + 1):
        fname = f"metrics_normal_agg{agg}_WU10_refined_rep{rep}.csv"
        mf = os.path.join(NB_DIR, fname)
        if not os.path.exists(mf):
            continue
        # Duas convenções de nome coexistem pro normal_traffic_summary_log_ desta família
        # "refined": os agregados históricos (20-640, gerados por scripts antigos já
        # deletados) usam "normal_traffic_summary_log_agg{agg}_..." (sem "normal_" duplicado);
        # os agregados novos (1280/2560, run_normal_isolado_s9_s11.py, e qualquer rep
        # reprocessado por run_unaffected_rerun.py) usam "normal_traffic_summary_log_
        # normal_agg{agg}_..." (com "normal_" -- suffix interno inclui isso, mesmo padrão
        # de metrics_/rtt_log_/traffic_capture_, sempre "normal_agg..."). Corrigido depois
        # de descobrir (investigação pedida pelo usuário sobre por que 1280/2560 não
        # escalavam além de 2 instâncias) que a primeira versão deste script só olhava a
        # convenção antiga e por isso achava "resumo ausente" pros 10 pontos novos -- não
        # era thread daemon falhando, era o arquivo certo com nome diferente do que o
        # script procurava.
        sf_new = os.path.join(NB_DIR, f"normal_traffic_summary_log_normal_agg{agg}_WU10_refined_rep{rep}.csv")
        sf_old = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg{agg}_WU10_refined_rep{rep}.csv")
        sf = sf_new if os.path.exists(sf_new) else sf_old
        real_rps = float("nan")
        if os.path.exists(sf):
            sdf = pd.read_csv(sf)
            sdf = sdf[sdf["total_requests"].notna()]
            if len(sdf):
                real_rps = sdf["real_rps"].sum()
        else:
            print(f"[AVISO] agg={agg} rep={rep}: normal_traffic_summary_log realmente ausente "
                  f"(nenhuma das 2 convenções de nome encontrada).")
        df = pd.read_csv(mf)
        peak_cpu = df["average_cpu_percent"].iloc[1:].max()
        mean_cpu = df["average_cpu_percent"].iloc[1:].mean()
        max_inst = int(df["num_instances"].max())
        escalou = bool((df["decision"] == "SCALE_UP").any())
        pos_fix = os.path.exists(os.path.join(PRE_DIR, fname))
        rows.append(dict(aggregate=agg, rep=rep, peak_cpu=peak_cpu, mean_cpu=mean_cpu,
                          max_inst=max_inst, escalou=escalou, pos_fix=pos_fix, real_rps=real_rps))

grid = pd.DataFrame(rows)
print(grid.to_string(index=False))

n_agg = len(AGGREGATE_TARGETS)
mat = np.full((n_agg, MAX_REPS), np.nan)
inst_mat = np.zeros((n_agg, MAX_REPS), dtype=int)
scaled_mat = np.zeros((n_agg, MAX_REPS), dtype=bool)
posfix_mat = np.zeros((n_agg, MAX_REPS), dtype=bool)
real_rps_mat = np.full((n_agg, MAX_REPS), np.nan)
for _, r in grid.iterrows():
    i = AGGREGATE_TARGETS.index(r["aggregate"])
    j = int(r["rep"]) - 1
    mat[i, j] = r["peak_cpu"]
    inst_mat[i, j] = r["max_inst"]
    scaled_mat[i, j] = r["escalou"]
    posfix_mat[i, j] = r["pos_fix"]
    real_rps_mat[i, j] = r["real_rps"]

fig, ax = plt.subplots(figsize=(11, 6.5 * n_agg / 6))
vmax = max(np.nanmax(mat), config.CPU_THRESHOLD_SCALE_UP)
im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")

ax.set_xticks(range(MAX_REPS))
ax.set_xticklabels([f"rep{r+1}" for r in range(MAX_REPS)], fontsize=8)
ax.set_yticks(range(n_agg))
ax.set_yticklabels([f"{a} rps" for a in AGGREGATE_TARGETS])
ax.set_xlabel("Repetição")
ax.set_ylabel("RPS agregado (tráfego normal isolado, WU=10)")

for i in range(n_agg):
    agg_nominal = AGGREGATE_TARGETS[i]
    for j in range(MAX_REPS):
        if np.isnan(mat[i, j]):
            continue
        marca = " ▲" if scaled_mat[i, j] else ""
        cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
        label = f"{mat[i, j]:.0f}%{marca}\n{inst_mat[i, j]} inst."
        real = real_rps_mat[i, j]
        # Teto do GERADOR DE TRÁFEGO do cliente (4 threads Python sob GIL, ver
        # investigação/changes.txt): acima de ~200 rps/thread (agregado/4 clientes fixos)
        # o cliente não consegue mais gerar a taxa nominal pedida -- real entregue fica bem
        # abaixo do alvo. Sinalizado por célula quando real < 80% do nominal, pra não
        # confundir "sistema aguenta esse RPS com poucas instâncias" com "o teste nunca
        # chegou a gerar esse RPS de verdade".
        if not np.isnan(real) and real < 0.8 * agg_nominal:
            label += f"\n(real: {real:.0f})"
        ax.text(j, i, label,
                ha="center", va="center", color=cor_texto, fontsize=7.5, fontweight="bold")
        # Borda verde de "pós-correção vs original" removida (changes.txt §116):
        # depois do lote 1 (§115) todas as reps estão pós-correção, a distinção
        # deixou de existir.
        if not np.isnan(real) and real < 0.8 * agg_nominal:
            rect2 = plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                   edgecolor="#d03b3b", linewidth=2.0, linestyle=":", zorder=6)
            ax.add_patch(rect2)

from matplotlib.patches import Patch
legend_elems = [Patch(facecolor="none", edgecolor="#d03b3b", linewidth=2.0, linestyle=":",
                      label="borda vermelha tracejada = teto do GERADOR DE TRÁFEGO atingido\n"
                            "(real entregue < 80% do nominal -- ver \"(real: N)\" na célula)")]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(0, -0.12), fontsize=8, frameon=False)

fig.colorbar(im, ax=ax, label="CPU de pico do run (%)")
ax.set_title(
    "Onde fica o teto de capacidade agora? -- tráfego normal isolado, pico de CPU por repetição\n"
    "▲ = SCALE_UP disparado -- 100% pós-correção do load balancer (changes.txt §102-104, §115)\n"
    "Linhas 1280/2560: teto do cliente (4 threads Python), NÃO do servidor -- ver anotação "
    "\"(real: N)\" e legenda",
    fontsize=10.5,
)
fig.tight_layout(rect=[0, 0.06, 1, 1])
out_path = os.path.join(OUT_DIR, "57_normal_isolado_teto_capacidade.png")
fig.savefig(out_path, dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")

print("\n--- Resumo por agregado ---")
for agg in AGGREGATE_TARGETS:
    sub = grid[grid["aggregate"] == agg]  # "aggregate" via [] -- .aggregate é método herdado do DataFrame
    if not len(sub):
        continue
    print(f"agg={agg:4d} (n={len(sub)}): pico médio={sub.peak_cpu.mean():.1f}%, "
          f"CPU média={sub.mean_cpu.mean():.1f}%, escalou {sub.escalou.sum()}/{len(sub)}, "
          f"real médio={sub.real_rps.mean():.0f} rps")
