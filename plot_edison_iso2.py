"""
Painéis EDiSON (fusão infra+RTT, Sotelo Monge 2019) sobre a bateria ISO2 ANTIGA
(experiment_results/edos_furtivo_robusto_iso2 — tráfego normal de carga única).

Para cada run gera, numa pasta própria, DOIS gráficos:
  1. edos_*.png    : o painel estatístico de sempre (CUSUM/Z/Entropia/Combinado
                     sobre o RTT) — representa o EDoS e os detectores de RTT;
  2. edison_*.png  : o painel EDiSON — X_cpu e X_app (entropia Rényi do RTT) com
                     previsão DES + intervalo adaptativo, e a faixa de FUSÃO que
                     marca o alerta W-EDoS (ambas inesperadas no mesmo t).

Uso:
  python3 plot_edison_iso2.py --run agg320_nwu5000_atk20pct_awu10000_rep1   # um só (demo)
  python3 plot_edison_iso2.py --all                                         # todos
"""
import argparse
import os
import re
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import edison
import plot_edos_furtivo_robusto_iso2 as base

D = "experiment_results/edos_furtivo_robusto_iso2"
OUT_RAIZ = "graficos_apresentacao/edison_iso2_antigo"
A0, A1, DUR = base.A0, base.A1, base.DUR        # 300, 450, 630
BASE_INI, BASE_FIM = base.BASE_INI, base.BASE_FIM
ATK, OK, INK, MUTED = "#d03b3b", "#1baf7a", "#1f2937", "#6b7280"
CPU_COR, APP_COR, FC_COR = "#c2410c", "#2563eb", "#7a3fd6"


def _no_ataque(grid, mask):
    m = mask & (grid >= A0) & (grid < A1)
    n = ((grid >= A0) & (grid < A1)).sum()
    return int(m.sum()), int(n)


def painel_edison(suf, out_dir):
    carga = base.carrega(suf)
    if carga is None:
        print("[faltando]", suf)
        return None
    m, r = carga
    atacado = "atk0pct" not in suf
    e = edison.detectar(m, r, base_ini=BASE_INI, base_fim=BASE_FIM)
    g = e["grid"]

    fig, (axc, axa, axf) = plt.subplots(3, 1, figsize=(11, 8.2), sharex=True,
                                        gridspec_kw=dict(height_ratios=[3, 3, 1.1], hspace=0.12))

    # ---- (a) X_cpu ----
    for ax in (axc, axa):
        ax.axvspan(0, BASE_INI, color="#f59e0b", alpha=0.08, lw=0)
        ax.axvspan(BASE_INI, BASE_FIM, color="#999999", alpha=0.10, lw=0)
        if atacado:
            ax.axvspan(A0, A1, color=ATK, alpha=0.06, lw=0)
    axc.fill_between(g, e["cpu_lo"], e["cpu_hi"], color=CPU_COR, alpha=0.13, lw=0, label="IP adaptativo (η·σ)")
    axc.plot(g, e["cpu_hat"], color=CPU_COR, lw=1.1, ls="--", alpha=0.9, label="previsão DES")
    axc.plot(g, e["x_cpu"], color=INK, lw=1.5, label="X_cpu observado")
    un = e["cpu_un"]
    axc.scatter(g[un], e["x_cpu"][un], s=22, color=ATK, zorder=5, label="inesperado")
    axc.axhline(60, color=ATK, ls=":", lw=0.8, alpha=0.6)
    axc.text(DUR - 2, 62, "scale up (60%)", ha="right", fontsize=7.5, color=ATK, alpha=0.8)
    axc.set_ylabel("X_cpu — CPU média\npor instância (%)")
    axc.set_ylim(0, max(100, np.nanmax(e["x_cpu"]) * 1.15))
    axc.set_title("(a) Infra: CPU observada vs. previsão DES + limiar adaptativo", fontsize=10.5, loc="left")
    axc.legend(fontsize=7.5, loc="upper left", ncol=2, framealpha=0.9)
    axc.grid(True, alpha=0.18)

    # ---- (b) X_app = entropia Rényi do RTT ----
    axa.fill_between(g, e["app_lo"], e["app_hi"], color=APP_COR, alpha=0.13, lw=0)
    axa.plot(g, e["app_hat"], color=APP_COR, lw=1.1, ls="--", alpha=0.9)
    axa.plot(g, e["x_app"], color=INK, lw=1.5)
    un = e["app_un"]
    axa.scatter(g[un], e["x_app"][un], s=22, color=ATK, zorder=5)
    axa.set_ylabel("X_app — entropia Rényi\ndo RTT (normalizada)")
    axa.set_ylim(0, 1.05)
    axa.set_title("(b) Aplicação: entropia do RTT observada vs. previsão DES + limiar adaptativo", fontsize=10.5, loc="left")
    axa.grid(True, alpha=0.18)

    # ---- (c) sintomas e fusão ----
    linhas = [("Symp(X_cpu)", e["cpu_un"]), ("Symp(X_app)", e["app_un"]), ("ALERTA EDiSON", e["alerta"])]
    passo = g[1] - g[0] if len(g) > 1 else 5
    for k, (nome, mask) in enumerate(linhas):
        y = len(linhas) - 1 - k
        cor_on = FC_COR if "ALERTA" in nome else ATK
        axf.barh(y, DUR, left=0, height=0.78, color="#eef0f3", edgecolor="white")
        for i, t in enumerate(g):
            if mask[i]:
                axf.barh(y, passo, left=t - passo, height=0.78, color=cor_on, edgecolor="white", linewidth=0.3)
        if atacado:
            na, nt = _no_ataque(g, mask)
            axf.text(DUR + 4, y, f"{na}/{nt} no ataque", va="center", fontsize=8, color=INK)
        else:
            axf.text(DUR + 4, y, f"{int(mask.sum())} FP", va="center", fontsize=8, color=INK)
    axf.set_yticks(range(len(linhas)))
    axf.set_yticklabels([n for n, _ in linhas][::-1], fontsize=8.5)
    axf.set_ylim(-0.5, len(linhas) - 0.5)
    axf.set_xlim(0, DUR)
    axf.set_xlabel("Tempo (s)")
    axf.set_title("(c) Sintomas por métrica e fusão W-EDoS (alerta = ambos no mesmo t)", fontsize=10.5, loc="left")
    for sp in ("top", "right", "left"):
        axf.spines[sp].set_visible(False)
    axf.tick_params(axis="y", length=0)
    if atacado:
        for ax in (axc, axa, axf):
            for x_ in (A0, A1):
                ax.axvline(x_, color=ATK, lw=0.9, ls="--", alpha=0.7)
    axf.set_xlim(0, DUR)

    na, nt = _no_ataque(g, e["alerta"])
    verd = (f"EDiSON alertou em {na}/{nt} janelas do ataque" if atacado
            else f"{int(e['alerta'].sum())} alertas (sem ataque = falsos positivos)")
    cor_t = ATK if (atacado and na > 0) else (INK if atacado else MUTED)
    fig.suptitle(f"EDiSON (fusão infra+RTT) — {suf}\n{verd}", fontsize=12, color=cor_t)
    fig.text(0.01, 0.005,
             f"Sotelo Monge et al. 2019 · X_cpu=CPU, X_app=entropia Rényi α={edison.RENYI_ALFA:g} (Shannon) do RTT · "
             f"previsão Double Exponential Smoothing (A={e['A']:g}, γ={e['gamma']:g}) · "
             f"intervalo de previsão adaptativo = previsão ± η·σ_baseline (η={e['eta']:g}; σ_cpu={e['cpu_sig']:.2f}, σ_app={e['app_sig']:.3f}) · "
             f"baseline (nível/tendência/σ) em t∈[{BASE_INI},{BASE_FIM}) · alerta W-EDoS = X_cpu E X_app inesperados no mesmo t (Def. 7)",
             fontsize=6.9, color=MUTED, va="bottom")
    fig.subplots_adjust(left=0.1, right=0.86, top=0.90, bottom=0.085)
    out = os.path.join(out_dir, f"edison_{suf}.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def _parse_suf(suf):
    """agg320_nwu10000_atk15pct_awu100000_rep2 -> (320,10000,100000,15,2);
    baseline agg320_nwu5000_atk0pct_rep1 -> (320,5000,None,0,1)."""
    m = re.match(r"agg(\d+)_nwu(\d+)_atk(\d+)pct(?:_awu(\d+))?_rep(\d+)", suf)
    if not m:
        return None
    rps, wu_n, pct, wu_a, rep = m.groups()
    return int(rps), int(wu_n), (int(wu_a) if wu_a else None), int(pct), int(rep)


def copia_painel_edos(suf, out_dir):
    """Copia o painel estatístico de RTT já existente p/ a pasta do run, ou o gera
    (as reps != 1 não foram pré-geradas na bateria original)."""
    origem = f"{base.OUT_DIR}/edos_furtivo_{suf}.png"
    destino = os.path.join(out_dir, f"edos_{suf}.png")
    if not os.path.exists(origem):
        p = _parse_suf(suf)
        if p is None:
            return None
        rps, wu_n, wu_a, pct, rep = p
        base.painel(rps, wu_n, wu_a, pct, rep)
    if os.path.exists(origem):
        shutil.copy(origem, destino)
        return destino
    return None


def processa(suf):
    out_dir = os.path.join(OUT_RAIZ, suf)
    os.makedirs(out_dir, exist_ok=True)
    pe = painel_edison(suf, out_dir)
    pd = copia_painel_edos(suf, out_dir)
    return out_dir, pe, pd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=str, help="sufixo de UM run (demo)")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT_RAIZ, exist_ok=True)
    if a.run:
        out_dir, pe, pd = processa(a.run)
        print("Pasta:", out_dir)
        print("EDiSON:", pe)
        print("EDoS  :", pd)
    elif a.all:
        import glob
        sufs = sorted(os.path.basename(f)[len("metrics_"):-4]
                      for f in glob.glob(f"{D}/metrics_*.csv"))
        for i, suf in enumerate(sufs, 1):
            processa(suf)
            if i % 20 == 0:
                print(f"  {i}/{len(sufs)}", flush=True)
        print(f"Concluído: {len(sufs)} runs em {OUT_RAIZ}/")
    else:
        ap.print_help()
