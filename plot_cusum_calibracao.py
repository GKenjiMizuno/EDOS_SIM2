"""
Gráficos 62 e 63 (changes.txt §125) -- calibração do CUSUM do EntCusumZV3.

62: alarme falso do CUSUM (por execução: >= 1 alarme nas 13 janelas de 20 s
    com t0 = 20..140 s) em execuções SEM ataque, por faixa de carga normal,
    uma curva por limiar h (em múltiplos do desvio do baseline). Mostra que o
    limiar padrão (5σ) dispara em quase metade ou mais das execuções limpas
    e que ~1000σ resolve até ~350 rps, mas não perto da saturação.
63: detecção do CUSUM com h = 1000σ num ataque W-EDoS (wedos_grid S4, 5%,
    WU=200.000). (a) CUSUM ao longo do tempo numa execução de ataque e num
    controle pareado sem ataque; (b) taxa de detecção sobre toda a grade
    W-EDoS por intensidade, com o alarme falso dos controles pareados.

Fontes (todas pós-correção, captura desligada): experiment_results/
deteccao_pos_lb/ (estatísticas por janela da reimplementação validada do
EntCusumZV3) e os rtt_log_*.csv brutos para a série temporal.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = "graficos_apresentacao/04_pos_loadbalancer"
D = "experiment_results/deteccao_pos_lb/"
os.makedirs(OUT, exist_ok=True)

INK, MUTED, GRID = "#1f2328", "#6e7781", "#e6e8eb"
ATK, CTRL, ALERTA = "#c2410c", "#2563eb", "#b91c1c"
H_VALS = [5, 20, 100, 1000, 10000]
H_CORES = ["#c7d7f0", "#93b4e3", "#5b8dd3", "#2c63b8", "#14366e"]  # sequencial: limiar maior = mais escuro
H_ESCOLHIDO = 1000
ATK0, ATK1 = 20, 160

plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False,
                     "axes.spines.right": False})


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * p, 100 * max(0, c - half), 100 * min(1, c + half)


t = pd.read_csv(D + "resultados/execucoes_avaliadas.csv")
w = pd.read_csv(D + "windows.csv.gz")
w = w[w.avaliada & w.t0.between(20, 140)]
t = t.merge(w.groupby("run_id").cusum_sd.max().rename("cmax"), left_on="run_id", right_index=True, how="left")
t["cmax"] = t["cmax"].fillna(0)

# ------------------------------------------------------------------ gráfico 62
neg = t[(~t.ataque) & (t.normal_wu == 10) & (t.normal_nom <= 640)].copy()
faixas = [(0, 25, "16-25"), (26, 50, "32-50"), (51, 100, "64-100"), (101, 200, "128-200"),
          (201, 350, "210-350"), (351, 640, "400-640")]
fig, ax = plt.subplots(figsize=(9.5, 5.6))
xs = np.arange(len(faixas))
ns = []
for k, (h, cor) in enumerate(zip(H_VALS, H_CORES)):
    vals, lo, hi = [], [], []
    for a, b, _ in faixas:
        s = neg[neg.normal_nom.between(a, b)]
        p, l, u = wilson(int((s.cmax > h).sum()), len(s))
        vals.append(p); lo.append(max(0, p - l)); hi.append(max(0, u - p))
        if k == 0:
            ns.append(len(s))
    destaque = h in (5, H_ESCOLHIDO)
    ax.errorbar(xs + (k - 2) * 0.05, vals, yerr=[lo, hi], color=cor, marker="o",
                markersize=7 if destaque else 5, linewidth=2.6 if destaque else 1.6,
                capsize=3, elinewidth=1, zorder=3 if destaque else 2,
                label=f"h = {h}σ" + (" (padrão atual)" if h == 5 else " (proposto)" if h == H_ESCOLHIDO else ""))
ax.axhline(5, color=MUTED, linestyle=":", linewidth=1)
ax.text(len(faixas) - 0.5, 6, "5% de alarme falso", color=MUTED, fontsize=8, ha="right")
ax.set_xticks(xs)
ax.set_xticklabels([f"{lab}\n(n={n})" for (_, _, lab), n in zip(faixas, ns)])
ax.set_xlabel("Carga de tráfego normal (rps agregado) — execuções SEM ataque")
ax.set_ylabel("Execuções com ≥ 1 alarme falso do CUSUM (%)")
ax.set_ylim(-3, 103)
ax.grid(axis="y", color=GRID)
ax.legend(title="Limiar do CUSUM", loc="upper left", fontsize=8.5, title_fontsize=9, frameon=False)
ax.set_title("Alarme falso do CUSUM em tráfego normal isolado, por carga e limiar\n"
             "Baseline: RTT nos primeiros 20 s · κ = 0,5σ · 13 janelas de 20 s (t = 20–160 s) por execução · "
             "barras = IC 95% (Wilson)", fontsize=10.5, color=INK)
fig.text(0.01, 0.01, "Fora do gráfico: 1280–2560 rps (n=12, 0% em todos os limiares) — RTT com desvio ~77 ms e teto do\n"
         "gerador de tráfego do cliente (changes.txt §112); o 0% ali é cegueira, não acerto.",
         fontsize=7.5, color=MUTED)
fig.tight_layout(rect=[0, 0.06, 1, 1])
p62 = os.path.join(OUT, "62_cusum_alarme_falso_por_carga_e_limiar.png")
fig.savefig(p62, dpi=150)
plt.close(fig)
print("Salvo:", p62)

# ------------------------------------------------------------------ gráfico 63
CFG = dict(cenario="S4", normal=300, pct=5.0, wu=200000)
atk_runs = t[(t.familia == "wedos_grid") & (t.cenario == CFG["cenario"]) & (t.pct == CFG["pct"]) &
             (t.atk_wu == CFG["wu"]) & (t.atk_fim.sub(160).abs() < 2)]
ctrl_runs = t[(t.familia == "normal_baseline") & (t.config == f"nb_agg{CFG['normal']}_wu10")]


def serie_cusum(path):
    d = pd.read_csv(path).sort_values("timestamp")
    tt = (d.timestamp - d.timestamp.min()).values
    # desconta os saltos do relógio de parede do WSL2 (lacunas > 2 s; §128)
    lac = np.diff(tt, prepend=tt[0])
    tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    v = d.rtt.values
    b = v[tt < 20]
    mu, sd = b.mean(), b.std(ddof=1)
    c, out = 0.0, np.empty(len(v))
    for i, x in enumerate(v):
        c = max(0.0, c + (x - mu) - 0.5 * sd)
        out[i] = c
    return tt, out / sd


def primeiro_alarme(rtt_path, h):
    # veredito no fim de cada janela de 20 s (passo 10 s), tempo corrigido -- igual ao gráfico 65
    tt, cs = serie_cusum(rtt_path)
    for fim in np.arange(20, 180 + 1e-9, 10):
        k = np.searchsorted(tt, fim) - 1
        if k >= 0 and cs[k] > h:
            return float(fim)
    return np.nan


# representantes: execução de ataque com o 1º alarme mediano; controle com CUSUM máx mediano
atk_runs = atk_runs.assign(alarme=[primeiro_alarme(p_, H_ESCOLHIDO) for p_ in atk_runs.rtt_path])
rep_atk = atk_runs.iloc[(atk_runs.alarme - atk_runs.alarme.median()).abs().argsort().iloc[0]]
rep_ctl = ctrl_runs.iloc[(ctrl_runs.cmax - ctrl_runs.cmax.median()).abs().argsort().iloc[0]]
m_atk = pd.read_csv(rep_atk.metrics_path)
su = m_atk[m_atk.decision == "SCALE_UP"].elapsed_time_s

# --- 63: exemplo no tempo (simplificado)
fig, a1 = plt.subplots(figsize=(10, 5.6))
a1.axvspan(ATK0, ATK1, color=ATK, alpha=0.07, lw=0)
a1.text((ATK0 + ATK1) / 2, 4e6, "período de ataque (20 a 160 s)", ha="center", color=ATK, fontsize=9.5)
for run, cor, nome in [(rep_ctl, CTRL, "Só tráfego normal (sem ataque)"), (rep_atk, ATK, "Tráfego normal + ataque W-EDoS")]:
    tt, cs = serie_cusum(run.rtt_path)
    b = pd.Series(cs).groupby((tt // 0.25).astype(int)).max()  # máximo por 0,25 s: preserva picos
    eh_ctrl = cor == CTRL
    a1.plot(b.index * 0.25, b.values, color=cor, lw=1.0 if eh_ctrl else 2.2, alpha=0.6 if eh_ctrl else 1,
            zorder=2 if eh_ctrl else 4, label=nome)
a1.axhline(H_ESCOLHIDO, color=INK, lw=1.5, ls="--", label=f"Limiar de alarme (h = {H_ESCOLHIDO}σ)")
if rep_atk.alarme == rep_atk.alarme:
    a1.axvline(rep_atk.alarme, color=ALERTA, lw=1.4)
    a1.text(rep_atk.alarme + 1.5, 3e3, f"ALARME\n(t = {rep_atk.alarme:.0f} s)", color=ALERTA, fontsize=9.5,
            fontweight="bold", zorder=6)
for s_ in su:
    a1.axvline(s_, color=MUTED, lw=1.2, ls="--", zorder=1)
    a1.text(s_ - 1.5, 3e3, f"autoscaler cria\nnova instância\n(t = {s_:.0f} s)", ha="right", fontsize=9, color=MUTED)
a1.set_yscale("symlog", linthresh=1)
a1.set_ylim(0, 2e7)
a1.set_xlim(0, 180)
a1.set_yticks([0, 1, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7])
a1.set_yticklabels(["0", "1", "10", "100", "1 mil", "10 mil", "100 mil", "1 milhão", "10 milhões"])
a1.set_xlabel("Tempo (s)")
a1.set_ylabel("Valor do CUSUM (em σ, escala log)")
a1.grid(axis="y", color=GRID)
a1.legend(loc="center right", bbox_to_anchor=(1, 0.66), fontsize=9, frameon=True, facecolor="white", edgecolor="none")
a1.set_title(f"CUSUM com e sem ataque — o alarme dispara quando a curva passa de {H_ESCOLHIDO}σ",
             fontsize=11.5, color=INK)
params = (f"Configuração: tráfego normal {CFG['normal']} rps (4 clientes, WU=10) · ataque = {CFG['pct']:g}% do tráfego = "
          f"{CFG['normal']*CFG['pct']/100:g} rps (4 atacantes, WU=200.000), de 20 a 160 s · execução de 180 s\n"
          f"Detector: RTT normal medido nos primeiros 20 s · κ = 0,5σ · h = {H_ESCOLHIDO}σ · "
          f"alarme verificado a cada 10 s (fim de cada janela de 20 s)\nTempo do RTT corrigido dos saltos de relógio do WSL2 (changes.txt §128)")
fig.text(0.01, 0.01, params, fontsize=8, color=MUTED, va="bottom")
fig.tight_layout(rect=[0, 0.10, 1, 1])
p63 = os.path.join(OUT, "63_cusum_exemplo_ataque_vs_normal.png")
fig.savefig(p63, dpi=150)
plt.close(fig)
print("Salvo:", p63)

# --- 64: resumo em barras (simplificado)
wg = t[(t.familia == "wedos_grid") & (t.atk_fim.sub(160).abs() < 2)].copy()
ctrls = t[(t.familia == "normal_baseline") & t.config.isin([f"nb_agg{c}_wu10" for c in (40, 100, 200, 300)])]
grupos = [("Sem ataque", ctrls, None)] + [(f"Ataque {p:g}%".replace(".", ","), wg[wg.pct == p], p) for p in (0.5, 1, 5, 10)]
fig, a2 = plt.subplots(figsize=(9, 5.6))
for i, (gn, s_, p) in enumerate(grupos):
    k, n = int((s_.cmax > H_ESCOLHIDO).sum()), len(s_)
    val = 100 * k / n
    a2.bar(i, val, width=0.6, color=MUTED if p is None else CTRL)
    a2.text(i, val + 2, f"{val:.0f}%", ha="center", fontsize=12, fontweight="bold", color=INK)
    a2.text(i, val + 9, f"{k} de {n} testes", ha="center", fontsize=8.5, color=MUTED)
    if p is not None:
        d = s_[s_.escalou_no_ataque]
        txt = (f"{len(d)} escalaram\n→ {int((d.cmax > H_ESCOLHIDO).sum())} de {len(d)}\ndetectados"
               if len(d) else "nenhum\nescalou")
        a2.text(i, 8, txt, ha="center", fontsize=7.8, color="white", fontweight="bold")
a2.set_xticks(range(len(grupos)))
a2.set_xticklabels([g[0] for g in grupos], fontsize=10)
a2.set_xlabel("Intensidade do ataque (% do tráfego normal)")
a2.set_ylabel("Testes em que o CUSUM deu alarme (%)")
a2.set_ylim(0, 118)
a2.set_yticks(range(0, 101, 20))
a2.grid(axis="y", color=GRID)
a2.set_axisbelow(True)
a2.set_title(f"Detecção pelo CUSUM (h = {H_ESCOLHIDO}σ) em todos os testes W-EDoS\n"
             "cinza = alarme falso (sem ataque) · azul = ataque detectado", fontsize=11.5, color=INK)
fig.text(0.01, 0.01, "Testes: cenários S1–S4 (tráfego normal de 40 a 300 rps), ataque com WU de 100.000 a 500.000, "
         "execuções de 180 s com ataque de 20 a 160 s.\n\"Sem ataque\" = mesmas cargas normais, 10 repetições cada.",
         fontsize=8, color=MUTED, va="bottom")
fig.tight_layout(rect=[0, 0.08, 1, 1])
p64 = os.path.join(OUT, "64_cusum_deteccao_por_intensidade.png")
fig.savefig(p64, dpi=150)
plt.close(fig)
print("Salvo:", p64)
print("exemplo ataque:", rep_atk.run_id, "| 1º alarme:", rep_atk.alarme, "| scale-up:", list(su))
