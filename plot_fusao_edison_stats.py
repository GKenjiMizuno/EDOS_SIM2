"""
Painéis da FUSÃO: analisador de infra (EDiSON adaptado) + métodos estatísticos de
RTT + a combinação 2×2 entre eles. Mesmo estilo dos painéis EDoS que o usuário
gosta (ex.: edos_multi_agg320_mix_atk25pct_awu50000_rep3.png), estendido:

  (a) EDiSON / INFRA  — carga computacional agregada da frota X_infra = nº
      instâncias × CPU/instância, com a FAIXA DE NORMALIDADE (μ+η·σ do baseline
      [60,300)) e a zona de anomalia marcada; nº de instâncias no eixo direito.
  (b) ESTATÍSTICO / RTT — RTT médio/s (log) com o portão 1,8× da baseline.
  (c) TIRAS DE VEREDITO a cada 10 s — INFRA(EDiSON), CUSUM, Z robusto, Entropia,
      Combinado-RTT, e a FUSÃO 2×2 (normal / ruído-RTT / EDoS clássico / W-EDoS
      furtivo).

A fusão NÃO é oráculo: as tiras individuais mostram que infra-só, RTT-só e o AND
cada um falha à sua maneira no furtivo (ver EDISON_ADAPTADO_INFRA_E_ML.txt). O
quadrante "infra sim / RTT não" = assinatura do W-EDoS furtivo.

Reusa plot_multi_endpoint_iso2 (carga + detectores de RTT). Saída:
  graficos_apresentacao/fusao_edison_estatistico/
Uso:
  python3 plot_fusao_edison_stats.py                       # todos os runs da bateria definitiva
  python3 plot_fusao_edison_stats.py 320 25 3              # um run (rps pct rep)
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import plot_multi_endpoint_iso2 as mep

OUT_DIR = "graficos_apresentacao/fusao_edison_estatistico"
os.makedirs(OUT_DIR, exist_ok=True)

A0, A1, DUR = mep.A0, mep.A1, mep.DUR
BI, BF = mep.BASE_INI, mep.BASE_FIM
ATK, INST, MUTED, INK = mep.ATK, mep.INST, mep.MUTED, mep.INK
MENU_STR, AWU, WUN = mep.MENU_STR, mep.ATAQUE_WU, mep.WU_N_EFETIVO
ETA = 3.0                      # faixa de normalidade da infra: μ + 3σ
INFRA_COR = "#2a78d6"
RPS_LIST = [160, 240, 320]
INTENS = [1, 5, 10, 15, 20, 25]
REPS = [1, 2, 3, 4, 5]
RPS_BASELINE = [120, 160, 200, 240, 280, 320]

# cores dos 4 quadrantes da fusão
Q_NORMAL, Q_RUIDO, Q_CLASSICO, Q_FURTIVO = "#1baf7a", "#f59e0b", "#d03b3b", "#7a3fd6"
QUAD_COR = {"normal": Q_NORMAL, "ruido": Q_RUIDO, "classico": Q_CLASSICO, "furtivo": Q_FURTIVO}
# rótulo honesto: o quadrante "infra sim / RTT não" é o PONTO CEGO do AND — ali o
# AND fica silencioso (falha). É a assinatura do furtivo, mas é inespecífico
# (furtivo OU carga legítima), por isso não é detecção confiável → motiva a ML.
QUAD_NOME = {"normal": "normal", "ruido": "ruído RTT (FP)",
             "classico": "EDoS clássico (AND dispara)",
             "furtivo": "infra-só — AND FALHA (furtivo ou carga legítima)"}
QUAD_TIT = {"normal": "normal", "ruido": "ruído RTT", "classico": "EDoS clássico",
            "furtivo": "INFRA-SÓ — AND FALHA (furtivo)"}


def infra_por_janela(m, jan):
    """Para cada janela de `jan` (coluna fim), diz se a infra está anômala:
    X_infra médio na janela > μ+η·σ do baseline. Retorna lista bool alinhada a jan."""
    ag = (m.num_instances * m.average_cpu_percent).values
    t = m.elapsed_time_s.values
    b = ag[(t >= BI) & (t < BF)]
    mu = b.mean() if len(b) else ag.mean()
    sd = b.std() if len(b) else ag.std()
    thr = mu + ETA * sd
    out = []
    for fim in jan.fim.values:
        w = ag[(t >= fim - 20) & (t < fim)]
        out.append(bool(len(w) and w.mean() > thr))
    return out, mu, sd, thr, ag, t


def quadrante(infra, rtt):
    if infra and rtt:
        return "classico"
    if infra and not rtt:
        return "furtivo"
    if (not infra) and rtt:
        return "ruido"
    return "normal"


def painel(rps, pct, rep):
    suf = mep.suf_de(rps, pct, rep)
    carga = mep.carrega(suf)
    if carga is None:
        print("[faltando]", suf)
        return None
    m, r = carga
    atacado = pct > 0
    mu_rtt, sd_rtt, jan = mep.detectores(r)
    infra_fire, mu_i, sd_i, thr_i, ag, tg = infra_por_janela(m, jan)
    jan = jan.assign(infra=infra_fire)
    jan = jan.assign(quad=[quadrante(i, c) for i, c in zip(jan.infra, jan.comb)])

    pos = jan[jan.fim > BF]                       # janelas após o baseline
    dentro = jan[(jan.fim - 20 >= A0) & (jan.fim <= A1)]

    fig = plt.figure(figsize=(15, 7.8))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.0, 1.75], hspace=0.08, wspace=0.26)
    ax = fig.add_subplot(gs[:, 0])        # (a) EDiSON / infra
    axr = fig.add_subplot(gs[0, 1])       # (b) RTT
    axs = fig.add_subplot(gs[1, 1], sharex=axr)   # (c) tiras de veredito

    # ----- (a) EDiSON: X_infra + faixa de normalidade -----
    ax2 = ax.twinx()
    if atacado:
        ax.axvspan(A0, A1, color=ATK, alpha=0.06, zorder=0)
    ax.axvspan(BI, BF, color="#999999", alpha=0.08, zorder=0)
    ax.plot(tg, ag, color=INFRA_COR, lw=1.8, zorder=3)
    ax.axhline(thr_i, color=ATK, ls="--", lw=1.1, zorder=2)
    ax.text(DUR - 2, thr_i + 2, f"faixa de normalidade  μ+{ETA:g}σ = {thr_i:.0f}",
            ha="right", fontsize=8, color=ATK)
    ax.fill_between(tg, thr_i, ag, where=(ag > thr_i), color=ATK, alpha=0.18, zorder=1)
    ax2.step(m.elapsed_time_s, m.num_instances, where="post", color=INST, lw=1.3, ls="--", alpha=0.85)
    ax.axvline(BI, color=MUTED, lw=0.8, ls=":")
    ax.axvline(BF, color=MUTED, lw=0.8, ls=":")
    ax.set_ylim(0, max(130, ag.max() * 1.12))
    ax2.set_ylim(0, 5)
    ax2.set_yticks([1, 2, 3, 4])
    ax2.set_ylabel("Nº de instâncias", color=INST)
    ax2.tick_params(colors=INST)
    ax.set_xlim(0, DUR)
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("EDiSON — carga computacional da frota\nX_infra = nº instâncias × CPU/instância (%)")
    ax.grid(True, alpha=0.2)
    ax.set_title("(a) Analisador de infraestrutura (EDiSON adaptado)", fontsize=11)
    ax.text((BI + BF) / 2, ax.get_ylim()[1] * 0.96, "baseline", fontsize=8, color=MUTED, ha="center", va="top")

    # ----- (b) RTT estatístico -----
    axr.axvspan(0, BI, color="#f59e0b", alpha=0.10, lw=0, zorder=0)
    axr.axvspan(BI, BF, color="#999999", alpha=0.12, lw=0, zorder=0)
    if atacado:
        axr.axvspan(A0, A1, color=ATK, alpha=0.06, lw=0, zorder=0)
    seg = r.groupby((r.t // 1).astype(int)).rtt.mean()
    axr.plot(seg.index + 0.5, seg.values, color="#1f2937", lw=1.0, zorder=3)
    axr.axhline(mep.RAZAO * mu_rtt, color="#7a3fd6", lw=1, ls=":")
    axr.text(DUR - 2, mep.RAZAO * mu_rtt * 1.25, "1,8× o RTT da baseline", ha="right", fontsize=8, color="#7a3fd6")
    if atacado:
        for x_ in (A0, A1):
            axr.axvline(x_, color=ATK, lw=1, ls="--")
    axr.set_yscale("log")
    axr.set_ylim(max(0.3, seg.min() * 0.5), max(50, seg.max() * 1.4))
    axr.set_xlim(0, DUR)
    axr.set_ylabel("RTT médio/s\n(ms, log)")
    axr.grid(True, axis="y", alpha=0.2)
    axr.tick_params(labelbottom=False)
    axr.set_title("(b) Métodos estatísticos sobre o RTT", fontsize=11)

    # ----- (c) tiras de veredito -----
    DETS = [("infra", "INFRA (EDiSON)"), ("cusum", "CUSUM"), ("z", "Z robusto"),
            ("ent", "Entropia JS"), ("comb", "Combinado-RTT"),
            ("and", "AND (EDiSON ∧ RTT)"), ("quad", "FUSÃO 2×2")]
    for k, (col, nome) in enumerate(DETS):
        y = len(DETS) - 1 - k
        axs.barh(y, BF, left=0, height=0.8, color="#d1d5db", edgecolor="white")  # baseline cinza
        for _, row in pos.iterrows():
            if col == "quad":
                cor = QUAD_COR[row.quad]
            elif col == "and":
                cor = ATK if (row.infra and row.comb) else mep.OK   # AND só dispara se os DOIS
            else:
                cor = ATK if row[col] else mep.OK
            axs.barh(y, 10, left=row.fim - 10, height=0.8, color=cor, edgecolor="white", linewidth=0.7)
        # rótulo à direita
        if col == "quad":
            if atacado and len(dentro):
                dom = dentro.quad.value_counts().idxmax()
                txt = f"ataque: {QUAD_NOME[dom]}"
            else:
                txt = ""
        elif col == "and":
            serie = (dentro.infra & dentro.comb) if atacado else (pos.infra & pos.comb)
            base = dentro if atacado else pos
            txt = f"{int(serie.sum())}/{len(base)} no ataque" if atacado else f"{int(serie.sum())}/{len(base)} FP"
        elif atacado:
            txt = f"{int(dentro[col].sum())}/{len(dentro)} no ataque"
        else:
            txt = f"{int(pos[col].sum())}/{len(pos)} FP"
        axs.text(DUR + 4, y, txt, va="center", fontsize=8, color=INK)
    axs.set_yticks(range(len(DETS)))
    axs.set_yticklabels([n for _, n in DETS][::-1], fontsize=8)
    axs.set_ylim(-0.5, len(DETS) - 0.5)
    axs.set_xlim(0, DUR)
    axs.set_xlabel("Tempo (s)")
    if atacado:
        for x_ in (A0, A1):
            axs.axvline(x_, color=ATK, lw=1, ls="--")
    for sp in ("top", "right", "left"):
        axs.spines[sp].set_visible(False)
    axs.tick_params(axis="y", length=0)

    # legenda
    h_leg = [Line2D([0], [0], color=INFRA_COR, lw=2, label="X_infra (carga da frota)"),
             Line2D([0], [0], color=ATK, lw=1.1, ls="--", label=f"faixa de normalidade μ+{ETA:g}σ"),
             Line2D([0], [0], color=INST, lw=1.3, ls="--", label="nº de instâncias"),
             Line2D([0], [0], color="#1f2937", lw=1.3, label="RTT médio/s"),
             Patch(color=Q_NORMAL, label="fusão: normal"), Patch(color=Q_RUIDO, label="fusão: ruído RTT"),
             Patch(color=Q_CLASSICO, label="fusão: EDoS clássico (AND dispara)"),
             Patch(color=Q_FURTIVO, label="fusão: infra-só (AND falha — furtivo ou carga legítima)")]
    fig.legend(handles=h_leg, loc="lower center", bbox_to_anchor=(0.5, 0.055), ncol=4, fontsize=8.2, frameon=False)

    # título com veredito dominante
    atk_rps = rps * pct / 100
    if atacado:
        titulo = (f"Normal {rps} rps (mix {MENU_STR}) + ataque {pct}% "
                  f"({atk_rps:g} rps, WU={AWU:,})").replace(",", ".")
        dom = dentro.quad.value_counts().idxmax() if len(dentro) else "normal"
        cor_tit = QUAD_COR.get(dom, INK)
        titulo += f"  —  {QUAD_TIT[dom]}"
    else:
        titulo = f"Normal isolado {rps} rps (mix {MENU_STR}) — sem ataque"
        cor_tit = INK
    fig.suptitle(titulo + f"   [rep{rep}]", fontsize=12, color=cor_tit)
    fig.text(0.01, 0.01,
             f"Execução: {suf} · {DUR}s · {f'ataque {A0}-{A1}s · ' if atacado else ''}"
             f"baseline t∈[{BI},{BF}) · EDiSON: X_infra=nº inst×CPU/inst, anomalia se > μ+{ETA:g}σ (μ={mu_i:.0f}, σ={sd_i:.0f}) · "
             f"WU_n efetivo ~{WUN:,}\n"
             f"Estatístico (EntCusumZV3): CUSUM κ=0,5σ h=1000σ · Z robusto · entropia JS · "
             f"Combinado-RTT = média>1,8× E (Z OU CUSUM) · AND = INFRA ∧ Combinado-RTT (silencioso no furtivo = FALHA) · "
             f"roxo = infra-só = ponto cego do AND → motiva ML".replace(",", "."),
             fontsize=7.4, color=MUTED, va="bottom")
    fig.subplots_adjust(left=0.065, right=0.90, top=0.90, bottom=0.17)
    nome_a = f"_awu{AWU}" if atacado else ""
    out = f"{OUT_DIR}/fusao_agg{rps}_mix_atk{pct}pct{nome_a}_rep{rep}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


if __name__ == "__main__":
    if len(sys.argv) == 4:
        rps, pct, rep = map(int, sys.argv[1:4])
        o = painel(rps, pct, rep)
        print("Salvo:", o)
    else:
        n = 0
        for rps in RPS_BASELINE:                 # baselines (0%)
            for rep in REPS:
                if painel(rps, 0, rep):
                    n += 1
        for rps in RPS_LIST:                     # grid de ataque
            for rep in REPS:
                for pct in INTENS:
                    if painel(rps, pct, rep):
                        n += 1
        print(f"\n{n} painéis salvos em {OUT_DIR}")
