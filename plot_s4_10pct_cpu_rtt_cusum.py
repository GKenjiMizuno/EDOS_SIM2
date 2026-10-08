"""
Gráfico 65 (changes.txt §128): o W-EDoS "mais próximo do ideal" (wedos_grid
S4, 10%, WU=400.000, 4 atacantes -- chega a 4 instâncias em 5/5 com ~0,6% de
erro normal). Dois painéis lado a lado, uma execução (a rep com erro normal
mediano das 5):
  (a) jornada da CPU + nº de instâncias, no estilo do gráfico 27;
  (b) RTT médio por segundo + faixas com o veredito de cada detector do
      EntCusumZV3 (CUSUM h=1000σ, Z-score, entropia, combinado com a média)
      no fim de cada janela de 20 s (passo 10 s).
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np
from EntCusumZV3 import (Z_K_RECOMENDADO, Z_FRAC_RECOMENDADA, ENTROPIA_BINS_RECOMENDADO,
                         ENTROPIA_JS_RECOMENDADO, bordas_log_baseline, divergencia_js,
                         histograma_faixas, z_robusto_params)
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# --normal: gráfico 66, mesmo desenho com o tráfego normal isolado do S4 (300 rps,
# sem ataque; normal_baseline agg300, rep10 = a mesma execução-controle do 63,
# escolhida lá pelo CUSUM máximo mediano das 10 reps).
# --c320=<pct> (§133): mesmo desenho do 67 (CUSUM com reset) sobre os dados
# já existentes do confirmacao_320 (§121): normal 320 rps com WU=10.000 +
# ataque WU=200.000 a 0/1/5% (0% = controle sem ataque), 180 s, 3 reps (usa a
# de erro normal mediano). Gera 69 (0%), 70 (1%), 71 (5%).
C320 = next((float(a.split("=")[1]) for a in sys.argv if a.startswith("--c320=")), None)
# --novos (§139): Z robusto contra o baseline (fração > Z_FRAC de amostras com
# z > Z_K) e entropia por divergência de Jensen-Shannon com faixas log do
# baseline -- ambos do EntCusumZV3 (§138). O combinado passa a usar o Z novo.
# Saída com sufixo _novos; versões sem a opção ficam intocadas.
NOVOS = "--novos" in sys.argv
NORMAL = "--normal" in sys.argv or C320 == 0
# --200s (§130): reexecução de 1 rep com 200 s (ataque continua em 20-160 s),
# para ver os detectores depois do fim do ataque. Gera 67 (combinado) / 68
# (normal) sem tocar no 65/66.
V200 = "--200s" in sys.argv
# --reset (§131, só com --200s): CUSUM com reinício após alarme -- quando a
# soma passa de h registra um alarme e volta a 0. Veredito da janela =
# houve >= 1 alarme dentro dela. Saída com sufixo _reset (67/68 sem reset
# ficam intocados).
RESET = ("--reset" in sys.argv and V200) or C320 is not None
DUR = 200 if V200 else 180
NOVO = V200 or C320 is not None  # contagem "no ataque / depois" e rodapé novos
if C320 is not None:
    D = "experiment_results/confirmacao_320"
    num = {0: 69, 1: 70, 5: 71}[int(C320)]
    OUT = f"graficos_apresentacao/04_pos_loadbalancer/{num}_320rps_wu10k_atk{C320:g}pct_cpu_e_rtt_detectores_reset.png"
    REPS = [f"agg320_nwu10000_atk{C320:g}pct_awu200000_rep{i}" for i in (1, 2, 3)]
elif V200:
    D = "experiment_results/s4_200s"
    OUT = ("graficos_apresentacao/04_pos_loadbalancer/68_s4_normal_isolado_200s_cpu_e_rtt_detectores.png" if NORMAL else
           "graficos_apresentacao/04_pos_loadbalancer/67_s4_10pct_wu400k_200s_cpu_e_rtt_detectores.png")
    REPS = ["normal_agg300_WU10_200s_rep1" if NORMAL else "S4_atk10pct_wu400000_200s_rep1"]
    if RESET:
        OUT = OUT.replace(".png", "_reset.png")
elif NORMAL:
    D = "experiment_results/normal_baseline"
    OUT = "graficos_apresentacao/04_pos_loadbalancer/66_s4_normal_isolado_cpu_e_rtt_detectores.png"
    REPS = ["normal_agg300_WU10_refined_rep10"]
else:
    D = "experiment_results/wedos_grid"
    OUT = "graficos_apresentacao/04_pos_loadbalancer/65_s4_10pct_wu400k_cpu_e_rtt_cusum.png"
    REPS = ["S4_atk10pct_wu400000_stage1a_rep1"] + [f"S4_atk10pct_wu400000_mlfill_rep{i}" for i in (2, 3, 4, 5)]
H = 1000
ATK_COLOR, INSTANCE_COLOR, OK_COLOR = "#d03b3b", "#555555", "#1baf7a"
CPU_COLOR = "#7a3fd6" if NORMAL else ATK_COLOR  # roxo = normal isolado, como no gráfico 27


def erro_normal(suf):
    x = pd.read_csv(f"{D}/normal_traffic_summary_log_{suf}.csv")
    x = x[x.total_requests.notna()]
    return 100 * x.errors.sum() / x.total_requests.sum()


erros = {s: erro_normal(s) for s in REPS}
suf = sorted(REPS, key=erros.get)[len(REPS) // 2]
m = pd.read_csv(f"{D}/metrics_{suf}.csv")
r = pd.read_csv(f"{D}/rtt_log_{suf}.csv").sort_values("timestamp")
# timestamp do rtt_log vem de time.time(); no WSL2 o relógio de parede salta
# ~3,6 s a cada ~36 s em relação ao time.monotonic() da simulação (§128).
# A 300 rps um silêncio real > 2 s é impossível: cada lacuna > 2 s é salto de
# relógio e é descontada. Resultado: duração 180,0 s e fim do ataque em 160 s.
t_bruto = (r.timestamp - r.timestamp.min()).values
lac = np.diff(t_bruto, prepend=t_bruto[0])
r["t"] = t_bruto - np.cumsum(np.where(lac > 2, lac, 0))
a0, a1 = 20, 160  # janela de ataque configurada

# Detectores do EntCusumZV3, recalculados no tempo corrigido. Janelas de 20 s
# com passo 10 s (t0 = 0, 10, ..., 160); veredito no fim da janela (t0 + 20).
Z_LIM, DH_LIM, RAZAO = 3.5, 1.5, 1.8
base = r[r.t < 20].rtt
mu, sd = base.mean(), base.std()
vals, tempo = r.rtt.values, r.t.values
c, cus = 0.0, np.empty(len(vals))
disparo = np.zeros(len(vals), dtype=bool)  # instantes em que o CUSUM com reset alarma
for i, v in enumerate(vals):
    c = max(0.0, c + (v - mu) - 0.5 * sd)
    if RESET and c > H * sd:
        disparo[i] = True
        c = 0.0
    cus[i] = c
vmin, vmax = vals.min(), vals.max()
if NOVOS:
    z_med, z_esc = z_robusto_params(base.values)
    bordas_ent = bordas_log_baseline(base.values, ENTROPIA_BINS_RECOMENDADO)
    p_base = histograma_faixas(base.values, bordas_ent)
jan, prev, ent_prev = [], None, None
for t0 in np.arange(0, DUR - 20 + 1, 10):
    msk = (tempo >= t0) & (tempo < t0 + 20)
    w = vals[msk]
    hist, _ = np.histogram(w, bins=10, range=(vmin, vmax))
    pr = hist / hist.sum()
    ent = stats.entropy(pr[pr > 0], base=2)
    dH = abs(ent - ent_prev) if ent_prev is not None else 0.0
    ent_prev = ent
    zmax = float(np.max(np.abs((w - prev[0]) / prev[1]))) if prev and prev[1] > 0 else 0.0
    prev = (w.mean(), w.std(ddof=1))
    cs = cus[np.where(msk)[0][-1]] / sd
    al_c = bool(disparo[msk].any()) if RESET else cs > H
    if NOVOS:
        frac_z = float(((w - z_med) / z_esc > Z_K_RECOMENDADO).mean())
        al_z = frac_z > Z_FRAC_RECOMENDADA
        al_e = divergencia_js(histograma_faixas(w, bordas_ent), p_base) > ENTROPIA_JS_RECOMENDADO
    else:
        al_z, al_e = zmax > Z_LIM, dH > DH_LIM
    jan.append(dict(fim=t0 + 20, media=w.mean(), cusum=al_c, z=al_z, ent=al_e,
                    n_disparos=int(disparo[msk].sum()),
                    comb=(w.mean() > RAZAO * mu) and (al_z or al_c),
                    comb5=(w.mean() > RAZAO * mu) and (zmax > Z_LIM or cs > 5)))
jan = pd.DataFrame(jan)
DETS = [("cusum", f"CUSUM c/ reset\n(> {H}σ)" if RESET else f"CUSUM\n(> {H}σ)"),
        ("z", (f"Z robusto\n(> {100 * Z_FRAC_RECOMENDADA:g}% c/ z > {Z_K_RECOMENDADO:g})" if NOVOS
               else f"Z-score\n(> {Z_LIM:g})").replace(".", ",")),
        ("ent", (f"Entropia JS\n(> {ENTROPIA_JS_RECOMENDADO:g})" if NOVOS
                 else f"Entropia\n(ΔH > {DH_LIM:g})").replace(".", ",")),
        ("comb", f"Combinado\n(média > {RAZAO:g}× e\nZ ou CUSUM)".replace(".", ","))]

fig = plt.figure(figsize=(15, 6.6))
gs = fig.add_gridspec(2, 2, height_ratios=[2.3, 1.25], hspace=0.08, wspace=0.28)
ax = fig.add_subplot(gs[:, 0])
axr = fig.add_subplot(gs[0, 1])
axs = fig.add_subplot(gs[1, 1], sharex=axr)

# (a) CPU + instâncias, estilo do gráfico 27
ax2 = ax.twinx()
if not NORMAL:
    ax.axvspan(a0, a1, color=ATK_COLOR, alpha=0.06, zorder=0)
ax.plot(m.elapsed_time_s, m.average_cpu_percent, color=CPU_COLOR, lw=1.8, zorder=3)
ax2.step(m.elapsed_time_s, m.num_instances, where="post", color=INSTANCE_COLOR, lw=1.3, ls="--", alpha=0.85)
ax.axhline(60, color=ATK_COLOR, ls=":", lw=0.9, alpha=0.6)
ax.text(158, 63, "limiar de scale up (60%)", ha="right", fontsize=8, color=ATK_COLOR, alpha=0.8)
ax.axhline(25, color="#2a78d6", ls=":", lw=0.9, alpha=0.8)
ax.text(158, 28, "limiar de scale down (25%)", ha="right", fontsize=8, color="#2a78d6")
ax.set_ylim(0, max(260, m.average_cpu_percent.max() * 1.1))
ax2.set_ylim(0, 5)
ax2.set_yticks([1, 2, 3, 4])
ax2.set_ylabel("Nº de instâncias", color=INSTANCE_COLOR)
ax2.tick_params(colors=INSTANCE_COLOR)
ax.set_xlim(0, DUR)
ax.set_xlabel("Tempo (s)")
ax.set_ylabel("CPU média por instância (%)")
ax.grid(True, alpha=0.2)
ax.set_title("(a) CPU e instâncias ao longo do teste", fontsize=11)
h_a = [Line2D([0], [0], color=CPU_COLOR, lw=2, label="CPU média"),
                   Line2D([0], [0], color=INSTANCE_COLOR, lw=1.3, ls="--", label="nº de instâncias (eixo direito)"),
                   Patch(color=ATK_COLOR, alpha=0.15, label="período de ataque")][:2 if NORMAL else 3]

# (b) RTT médio por segundo + veredito de cada detector
axr.axvspan(0, 20, color="#999999", alpha=0.12, lw=0, zorder=0)
if not NORMAL:
    axr.axvspan(a0, a1, color=ATK_COLOR, alpha=0.06, lw=0, zorder=0)
seg = r.groupby((r.t // 1).astype(int)).rtt.mean()
axr.plot(seg.index + 0.5, seg.values, color="#1f2937", lw=1.4, zorder=3)
axr.axhline(RAZAO * mu, color="#7a3fd6", lw=1, ls=":")
axr.text(DUR - 2, RAZAO * mu * 1.25, f"{RAZAO:g}× o RTT normal (regra da média)".replace(".", ","),
         ha="right", fontsize=8, color="#7a3fd6")
if not NORMAL:
    for x_ in (a0, a1):
        axr.axvline(x_, color=ATK_COLOR, lw=1, ls="--")
    axr.text(a0 + 1, 1.2e3, "ataque começa", fontsize=8, color=ATK_COLOR)
    axr.text(a1 - 1, 1.2e3, "ataque termina", fontsize=8, color=ATK_COLOR, ha="right")
else:
    axr.text(100, 1.2e3, "sem ataque durante todo o teste", fontsize=8, color="#6b7280", ha="center")
axr.text(10, 1.2e3, "baseline", fontsize=8, color="#6b7280", ha="center")
axr.set_yscale("log")
axr.set_ylim(0.5, 3e3)
axr.set_xlim(0, DUR)
axr.set_ylabel("RTT médio por segundo\n(ms, escala log)")
axr.grid(True, axis="y", alpha=0.2)
axr.tick_params(labelbottom=False)
axr.set_title("(b) RTT e o veredito de cada detector a cada 10 s", fontsize=11)

dentro = jan[(jan.fim >= 40) & (jan.fim <= 160)]  # 13 janelas inteiras dentro do ataque (no normal: as mesmas 13)
for k, (col, nome) in enumerate(DETS):
    y = len(DETS) - 1 - k
    axs.barh(y, 20, left=0, height=0.78, color="#d1d5db", edgecolor="white")
    for _, row in jan.iterrows():
        axs.barh(y, 10, left=row.fim, height=0.78, color=ATK_COLOR if row[col] else OK_COLOR,
                 edgecolor="white", linewidth=0.8)
    primeiro = jan[jan[col]].fim.min()
    if NOVO:
        depois = jan[jan.fim - 20 >= a1]  # janelas inteiras depois do fim do ataque
        tudo = jan[jan.fim >= 40]
        txt = (f"{int(tudo[col].sum())}/{len(tudo)} alarmes\nfalsos" if NORMAL else
               f"{int(dentro[col].sum())}/{len(dentro)} no ataque\n{int(depois[col].sum())}/{len(depois)} depois")
    else:
        txt = (f"{int(dentro[col].sum())}/{len(dentro)} alarmes\nfalsos" if NORMAL
               else f"{int(dentro[col].sum())}/{len(dentro)} no ataque")
    axs.text(DUR + 1, y, txt, va="center", fontsize=8, color="#1f2937")
axs.set_yticks(range(len(DETS)))
axs.set_yticklabels([n for _, n in DETS][::-1], fontsize=8)
axs.set_ylim(-0.5, len(DETS) - 0.5)
axs.set_xlim(0, DUR)
axs.set_xlabel("Tempo (s)")
for x_ in (() if NORMAL else (a0, a1)):
    axs.axvline(x_, color=ATK_COLOR, lw=1, ls="--")
for sp in ("top", "right", "left"):
    axs.spines[sp].set_visible(False)
axs.tick_params(axis="y", length=0)
h_b = [Line2D([0], [0], color="#1f2937", lw=1.4, label="RTT médio por segundo"),
                    Patch(color="#d1d5db", label="baseline (aprendendo o normal)"),
                    Patch(color=OK_COLOR, label="detector diz: normal"),
                    Patch(color=ATK_COLOR, label="detector diz: ataque")][::1]
fig.legend(handles=h_a + h_b, loc="lower center", bbox_to_anchor=(0.5, 0.11 if C320 is not None else 0.09 if RESET else 0.075), ncol=4, fontsize=8.5, frameon=False)

if C320 is not None:
    fig.suptitle(("Normal 320 rps com WU = 10.000, sem ataque" if NORMAL else
                  f"Normal 320 rps com WU = 10.000 + ataque de {C320:g}% ({320 * C320 / 100:g} rps, WU = 200.000)".replace(".2 rps", ",2 rps"))
                 + " — CUSUM com reset", fontsize=12.5)
else:
  fig.suptitle(("Cenário S4 sem ataque: só tráfego normal de 300 rps (WU = 10)" if NORMAL else
                "W-EDoS no cenário S4: tráfego normal 300 rps + ataque de 10% (30 rps, WU = 400.000)")
             + (" — teste de 200 s" if V200 else "") + (" — CUSUM com reset" if RESET else ""), fontsize=12.5)
if C320 is not None:
    linha1 = (f"Execução: {suf} (erro normal mediano entre 3 reps: {erros[suf]:.2f}%; dados do §121) · tráfego normal 4 clientes × 80 rps, "
              f"WU=10.000 · " + ("sem ataque · alarmes falsos contados em todas as janelas após o baseline (fim em 40-180 s)\n"
              "ATENÇÃO: o sistema escala aos 5 s pelo pico de CPU do arranque, e o baseline (0-20 s) é aprendido nesse período de sobrecarga (§121)\n" if NORMAL else
              f"4 atacantes × {320 * C320 / 100 / 4:g} rps · ataque de {a0:.0f} a {a1:.0f} s\n\"depois\" = janela inteira após o fim do ataque (fim em 180 s) · ".replace("0.8", "0,8")
              + "ATENÇÃO: o sistema escala aos 5 s pelo pico de CPU do arranque, e o baseline (0-20 s) é aprendido nesse período de sobrecarga (§121)\n"))
else:
  linha1 = (f"Execução: {suf} (1 repetição, {DUR} s) · tráfego normal 4 clientes × 75 rps, WU=10 · "
          + ("sem ataque · alarmes falsos contados em todas as janelas após o baseline (fim em 40-200 s)\n" if NORMAL else
             f"4 atacantes × 7,5 rps · ataque de {a0:.0f} a {a1:.0f} s · \"depois\" = janelas inteiras após o fim do ataque (fim em 180-200 s)\n")
          ) if V200 else (f"Execução: {suf} (mesmo controle do gráfico 63; erro normal {erros[suf]:.2f}%) · tráfego normal 4 clientes × 75 rps, "
          f"WU=10 · sem ataque · alarmes contados nas mesmas 13 janelas do gráfico 65 (fim em 40-160 s)\n") if NORMAL else (
          f"Execução: {suf} (erro normal mediano entre 5 reps: {erros[suf]:.2f}%) · tráfego normal 4 clientes × 75 rps, WU=10 · "
          f"4 atacantes × 7,5 rps · ataque de {a0:.0f} a {a1:.0f} s\n")
fig.text(0.01, 0.01, linha1 +
         f"Detectores (EntCusumZV3): janelas de 20 s, passo 10 s, veredito no fim da janela · baseline = RTT dos primeiros 20 s · "
         f"CUSUM κ = 0,5σ, h = {H}σ" + (" com reset (zera ao alarmar; janela = ataque se houve alarme nela)" if RESET else "") + ("\n" if RESET else " · ") + (f"Z robusto = (RTT − mediana)/(1,4826·MAD) do baseline, alarme se > {100 * Z_FRAC_RECOMENDADA:g}".replace(".", ",") + f"% das amostras com z > {Z_K_RECOMENDADO:g} · "
    f"entropia: divergência de Jensen-Shannon janela×baseline, {ENTROPIA_BINS_RECOMENDADO} faixas log + transbordo (§138)\n" if NOVOS else
    "Z = maior |z| da janela contra a janela anterior · entropia de 10 faixas do RTT\n") +
         (f"Combinado = média da janela > {RAZAO:g}× o baseline E (" + ("Z robusto" if NOVOS else f"Z > {Z_LIM:g}") +
          " OU CUSUM > h) · tempo do RTT corrigido dos saltos de relógio do WSL2").replace("1.8", "1,8").replace("3.5", "3,5"),
         fontsize=7.8, color="#6b7280")
fig.subplots_adjust(left=0.05, right=0.93, top=0.89, bottom=0.29 if C320 is not None else 0.27 if RESET else 0.25)
if NOVOS:
    OUT = OUT.replace(".png", "_novos.png")
fig.savefig(OUT, dpi=150)
print("Salvo:", OUT, "| execução:", suf)
print("SCALE_UPs:", list(m[m.decision == "SCALE_UP"].elapsed_time_s), "SCALE_DOWNs:", list(m[m.decision == "SCALE_DOWN"].elapsed_time_s))
print(jan.round(2).to_string(index=False))
