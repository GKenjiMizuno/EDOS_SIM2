"""
Gráfico 72 (changes.txt §142): resumo agregado dos detectores ANTES x DEPOIS do
ajuste de Z-score e entropia (§138), sobre TODAS as execuções de avaliação.

Execuções: populações do §117/§129/§138 (execucoes_avaliadas.csv; sem S9-S11,
sem captura) -- só as reps PARES (avaliação), que não foram usadas para escolher
os parâmetros. Por execução, no tempo do rtt_log corrigido dos saltos de relógio
(§128): baseline = RTT em t < 20 s; 13 janelas de 20 s com t0 = 20..140; alarme
da execução = >= 1 janela.
  Z         antes: maior |z| da janela contra média/desvio da janela anterior > 3,5
            depois: Z robusto (EntCusumZV3, z_modo='robusto_baseline'): > 1,9% das
                    amostras com (RTT - mediana_base)/(1,4826·MAD_base) > 15
  Entropia  antes: 10 faixas lineares mín-máx do arquivo, |ΔH| vs janela anterior > 1,5
            depois: divergência de Jensen-Shannon janela x baseline (10 faixas log
                    do baseline + transbordo) > 0,078
  CUSUM     antes: h = 5σ (padrão original); depois: h = 1000σ (§125, igual aos
            gráficos 62-71)
  Combinado média da janela > 1,8x o baseline E (Z OU CUSUM), com o Z e o CUSUM
            da respectiva versão
Barras de erro: IC 95% de Wilson. Tabela: resultados/T21_antes_depois_execucoes.csv
"""
import os
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from EntCusumZV3 import (ENTROPIA_BINS_RECOMENDADO, ENTROPIA_JS_RECOMENDADO, Z_FRAC_RECOMENDADA,
                         Z_K_RECOMENDADO, bordas_log_baseline, divergencia_js, entropia_shannon,
                         histograma_faixas, z_robusto_params)

R = "experiment_results/deteccao_pos_lb/resultados"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/02_depois_ajuste_z_entropia"
OUT = os.path.join(OUT_DIR, "72_deteccao_antes_depois_ajuste_z_entropia.png")
H_ANTES, H_DEPOIS, RAZAO = 5.0, 1000.0, 1.8
POS_T0 = np.arange(20, 141, 10)
ANTES, DEPOIS, INK, MUTED, GRID = "#9ca3af", "#2563eb", "#1f2937", "#6b7280", "#e5e7eb"


def processa(args):
    run_id, path = args
    r = pd.read_csv(path).sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    v = r.rtt.values
    b = v[tt < 20]
    mu, sd = b.mean(), b.std()
    c, cus = 0.0, np.empty(len(v))
    for i, x in enumerate(v):
        c = max(0.0, c + (x - mu) - 0.5 * sd)
        cus[i] = c
    cus /= sd
    z_med, z_esc = z_robusto_params(b)
    bordas = bordas_log_baseline(b, ENTROPIA_BINS_RECOMENDADO)
    p_base = histograma_faixas(b, bordas)
    vmin, vmax = v.min(), v.max()
    al = dict.fromkeys(["z_a", "z_d", "e_a", "e_d", "c_a", "c_d", "comb_a", "comb_d"], False)
    prev, ent_prev = None, None
    for t0 in np.arange(0, 141, 10):  # desde 0 para a cadeia "janela anterior" do Z/entropia antigos
        m = (tt >= t0) & (tt < t0 + 20)
        if m.sum() < 10:
            prev, ent_prev = None, None
            continue
        w = v[m]
        zmax = float(np.max(np.abs((w - prev[0]) / prev[1]))) if prev and prev[1] > 0 else 0.0
        prev = (w.mean(), w.std(ddof=1))
        h, _ = np.histogram(w, bins=10, range=(vmin, vmax))
        ent = entropia_shannon(h / h.sum())
        dH = abs(ent - ent_prev) if ent_prev is not None else 0.0
        ent_prev = ent
        if t0 not in POS_T0:
            continue
        cs = cus[np.where(m)[0][-1]]
        media_alta = w.mean() > RAZAO * mu
        z_a, z_d = zmax > 3.5, float(((w - z_med) / z_esc > Z_K_RECOMENDADO).mean()) > Z_FRAC_RECOMENDADA
        e_a, e_d = dH > 1.5, divergencia_js(histograma_faixas(w, bordas), p_base) > ENTROPIA_JS_RECOMENDADO
        c_a, c_d = cs > H_ANTES, cs > H_DEPOIS
        for k, val in (("z_a", z_a), ("z_d", z_d), ("e_a", e_a), ("e_d", e_d), ("c_a", c_a), ("c_d", c_d),
                       ("comb_a", media_alta and (z_a or c_a)), ("comb_d", media_alta and (z_d or c_d))):
            al[k] = al[k] or bool(val)
    return dict(run_id=run_id, **al)


def wilson(k, n, z=1.96):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * p, 100 * max(0.0, c - h), 100 * min(1.0, c + h)


if __name__ == "__main__":
    t = pd.read_csv(os.path.join(R, "execucoes_avaliadas.csv"))
    ok_int = (t.atk_ini.sub(20).abs() < 1) & (t.atk_fim.sub(160).abs() < 2)
    gil = t.gil.fillna(False).astype(bool)
    cap = t.captura.astype(bool)
    t["POS"] = t.ataque & ~gil & ok_int & ~cap
    t["POS_D"] = t.POS & t.escalou_no_ataque
    t["NEG"] = ~t.ataque & (t.normal_nom <= 640) & (t.normal_wu == 10) & ~cap
    t = t[(t.POS | t.NEG) & (t.rep % 2 == 0)].copy()  # só avaliação

    with Pool(6) as p:
        E = pd.DataFrame(p.map(processa, list(zip(t.run_id, t.rtt_path))))
    E = E.merge(t[["run_id", "POS", "POS_D", "NEG", "normal_nom"]], on="run_id")
    os.makedirs(R, exist_ok=True)
    E.to_csv(os.path.join(R, "T21_antes_depois_execucoes.csv"), index=False)

    metodos = [("Z-score", "z"), ("Entropia", "e"), ("CUSUM", "c"), ("Combinado\n(regra do EntCusumZV3)", "comb")]
    paineis = [("NEG", "(a) Alarme falso\nexecuções SEM ataque (menor é melhor)"),
               ("POS", "(b) Detecção\ntodas as execuções COM ataque"),
               ("POS_D", "(c) Detecção\nataques que causaram escalonamento")]
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.6), sharey=True)
    x = np.arange(len(metodos))
    linhas = []
    for ax, (pop, titulo) in zip(axs, paineis):
        sub = E[E[pop]]
        n = len(sub)
        for j, (cor, suf) in enumerate(((ANTES, "_a"), (DEPOIS, "_d"))):
            for i, (nome, chave) in enumerate(metodos):
                k = int(sub[chave + suf].sum())
                val, lo, hi = wilson(k, n)
                xi = i + (j - 0.5) * 0.36
                ax.bar(xi, val, width=0.34, color=cor, zorder=2)
                ax.errorbar(xi, val, yerr=[[val - lo], [hi - val]], color=INK, lw=0.9, capsize=2.5, zorder=3)
                ax.text(xi, hi + 1.5, f"{val:.0f}%", ha="center", fontsize=8, color=INK)
                linhas.append(dict(populacao=pop, metodo=nome.split("\n")[0], versao="antes" if suf == "_a" else "depois",
                                   k=k, n=n, pct=round(val, 1), ic95=f"{lo:.1f}-{hi:.1f}"))
        ax.set_title(f"{titulo} (n = {n})", fontsize=10.5, color=INK)
        ax.set_xticks(x)
        ax.set_xticklabels([m[0] for m in metodos], fontsize=9)
        ax.set_ylim(0, 112)
        ax.set_yticks(range(0, 101, 20))
        ax.grid(axis="y", color=GRID, zorder=0)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axs[0].set_ylabel("Execuções com ≥ 1 alarme nas 13 janelas do ataque (%)")
    fig.legend(handles=[Patch(color=ANTES, label="antes: Z > 3,5 vs janela anterior · entropia ΔH > 1,5 · CUSUM 5σ"),
                        Patch(color=DEPOIS, label="depois: Z robusto (>1,9% c/ z>15) · entropia Jensen-Shannon > 0,078 · CUSUM 1000σ")],
               loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=2, fontsize=9, frameon=False)
    fig.suptitle("Detectores estatísticos antes e depois do ajuste de Z-score e entropia", fontsize=13, color=INK, y=0.995)
    fig.text(0.01, 0.01,
             "Execuções de avaliação (repetições pares, não usadas para escolher os parâmetros) · sem S9-S11 (teto do gerador) · "
             "tráfego normal 16-640 rps, WU=10 · ataque 20-160 s · tempo do RTT corrigido (§128)\n"
             "Combinado = média da janela > 1,8× o baseline E (Z OU CUSUM) da respectiva versão · barras de erro = IC 95% (Wilson) · "
             "parâmetros e calibração: changes.txt §129 e §138",
             fontsize=7.8, color=MUTED, va="bottom")
    fig.tight_layout(rect=[0, 0.06, 1, 0.92])
    os.makedirs(OUT_DIR, exist_ok=True)
    fig.savefig(OUT, dpi=150)
    pd.DataFrame(linhas).to_csv(os.path.join(R, "T21_antes_depois_resumo.csv"), index=False)
    print("Salvo:", OUT)
    print(pd.DataFrame(linhas).pivot_table(index="metodo", columns=["populacao", "versao"], values="pct").round(1))
