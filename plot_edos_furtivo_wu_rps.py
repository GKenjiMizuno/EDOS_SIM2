"""
Gráficos de detecção da bateria EDoS furtivo 3D (changes.txt §147):
RPS agregado {160,320} x WU_normal {5000,10000} x WU_ataque {50000,100000,200000}
x intensidade {1,5,10}% (+ 0% normal isolado). Tempo 240 s, ataque 60-180 s.
Modelo Sotelo Monge: WU_ataque > WU_normal (endpoint pesado vs leve).

Mesmo desenho dos gráficos 65-71 / §145 (painel a: CPU+instâncias; painel b: RTT
médio/s + faixa de veredito de cada detector a cada 10 s), detectores recomendados
do EntCusumZV3 (§143): CUSUM 1000σ com reset, Z robusto, entropia Jensen-Shannon,
combinado (média > 1,8x E (Z OU CUSUM)).

Baseline = RTT em t em [15,60) -- a janela de pré-ataque APARADA dos ~15 s de
arranque (cold-start). Isso corrige a contaminação do σ/cauda pelo pico de arranque
que, no baseline cheio [0,60), produzia furtividade falsa (ver investigação dos
gráficos 69/71). O resumo também traz a contagem com baseline cheio para comparação.
Tempo do rtt_log corrigido dos saltos de relógio do WSL2 (§128).

Saídas em graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/
04_edos_furtivo_wu_rps/:
  - um painel por célula (40);
  - 2 heatmaps (Combinado e CUSUM): grade 2x2 de (RPS x WU_normal), cada um
    WU_ataque x intensidade, destacando células FURTIVAS (escalou, 0 alarmes).
Tabela: experiment_results/edos_furtivo_wu_rps/resumo_edos_furtivo_wu_rps.csv

Uso: python3 plot_edos_furtivo_wu_rps.py [--heatmap-only]
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

from EntCusumZV3 import (ENTROPIA_BINS_RECOMENDADO, ENTROPIA_JS_RECOMENDADO, Z_FRAC_RECOMENDADA,
                         Z_K_RECOMENDADO, bordas_log_baseline, divergencia_js,
                         histograma_faixas, z_robusto_params)

D = "experiment_results/edos_furtivo_wu_rps"
OUT_DIR = ("graficos_apresentacao/04_pos_loadbalancer/03_deteccao_estatistica/"
           "04_edos_furtivo_wu_rps")
os.makedirs(OUT_DIR, exist_ok=True)
RPS_LIST = [160, 320]
WU_NORMAL = [5000, 10000]
WU_ATAQUE = [50000, 100000, 200000]
INTENS = [1, 5, 10]
A0, A1, DUR = 60, 180, 240            # ataque 60-180
BASE_INI, BASE_FIM = 15, 60           # baseline APARADO do arranque
H, RAZAO = 1000.0, 1.8
ATK, INST, OK, INK, MUTED, GRID = "#d03b3b", "#555555", "#1baf7a", "#1f2937", "#6b7280", "#e5e7eb"


def suf_de(rps, wu_n, wu_a, pct):
    if pct == 0:
        return f"agg{rps}_nwu{wu_n}_atk0pct_rep1"
    return f"agg{rps}_nwu{wu_n}_atk{pct}pct_awu{wu_a}_rep1"


def carrega(suf):
    mp, rp = f"{D}/metrics_{suf}.csv", f"{D}/rtt_log_{suf}.csv"
    if not (os.path.exists(mp) and os.path.exists(rp)):
        return None
    m = pd.read_csv(mp)
    r = pd.read_csv(rp).sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    r = r.assign(t=tt - np.cumsum(np.where(lac > 2, lac, 0)))
    return m, r


def detectores(r, base_ini=BASE_INI):
    """Veredito por janela (fim 20..DUR, passo 10) de cada detector. baseline em [base_ini,BASE_FIM)."""
    v = r.rtt.values
    tt = r.t.values
    b = v[(tt >= base_ini) & (tt < BASE_FIM)]
    if len(b) < 10:
        b = v[tt < BASE_FIM]
    mu, sd = b.mean(), b.std()
    z_med, z_esc = z_robusto_params(b)
    bordas = bordas_log_baseline(b, ENTROPIA_BINS_RECOMENDADO)
    p_base = histograma_faixas(b, bordas)
    c, cus = 0.0, np.empty(len(v))
    disp = np.zeros(len(v), dtype=bool)
    for i, x in enumerate(v):
        c = max(0.0, c + (x - mu) - 0.5 * sd)
        if c > H * sd:
            disp[i] = True
            c = 0.0
        cus[i] = c
    jan = []
    for t0 in np.arange(0, DUR - 20 + 1, 10):
        msk = (tt >= t0) & (tt < t0 + 20)
        if msk.sum() < 10:
            continue
        w = v[msk]
        frac_z = float(((w - z_med) / z_esc > Z_K_RECOMENDADO).mean())
        al_z = frac_z > Z_FRAC_RECOMENDADA
        al_e = divergencia_js(histograma_faixas(w, bordas), p_base) > ENTROPIA_JS_RECOMENDADO
        al_c = bool(disp[msk].any())
        jan.append(dict(fim=t0 + 20, media=w.mean(), cusum=al_c, z=al_z, ent=al_e,
                        comb=(w.mean() > RAZAO * mu) and (al_z or al_c)))
    return mu, sd, pd.DataFrame(jan), cus / sd


def painel(rps, wu_n, wu_a, pct):
    suf = suf_de(rps, wu_n, wu_a, pct)
    carga = carrega(suf)
    if carga is None:
        print("[faltando]", suf)
        return None
    m, r = carga
    mu, sd, jan, _ = detectores(r)
    atacado = pct > 0
    dentro = jan[(jan.fim - 20 >= A0) & (jan.fim <= A1)]
    depois = jan[jan.fim - 20 >= A1]
    escalou_atk = bool(((m.decision == "SCALE_UP") & (m.elapsed_time_s > A0) & (m.elapsed_time_s <= A1)).any())
    try:
        ns = pd.read_csv(f"{D}/normal_traffic_summary_log_{suf}.csv")
        ns = ns[ns.total_requests.notna()]
        err_norm = 100 * ns.errors.sum() / ns.total_requests.sum()
    except (FileNotFoundError, ZeroDivisionError):
        err_norm = np.nan
    # comparação: baseline cheio (sem aparar) -> comb no ataque
    _, _, jan_full, _ = detectores(r, base_ini=0)
    dentro_full = jan_full[(jan_full.fim - 20 >= A0) & (jan_full.fim <= A1)]
    comb_full = int(dentro_full.comb.sum()) if atacado else int(jan_full[jan_full.fim > BASE_FIM].comb.sum())

    fig = plt.figure(figsize=(15, 6.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.3, 1.25], hspace=0.08, wspace=0.28)
    ax = fig.add_subplot(gs[:, 0])
    axr = fig.add_subplot(gs[0, 1])
    axs = fig.add_subplot(gs[1, 1], sharex=axr)
    cpu_cor = ATK if atacado else "#7a3fd6"

    ax2 = ax.twinx()
    if atacado:
        ax.axvspan(A0, A1, color=ATK, alpha=0.06, zorder=0)
    ax.plot(m.elapsed_time_s, m.average_cpu_percent, color=cpu_cor, lw=1.8, zorder=3)
    ax2.step(m.elapsed_time_s, m.num_instances, where="post", color=INST, lw=1.3, ls="--", alpha=0.85)
    ax.axhline(60, color=ATK, ls=":", lw=0.9, alpha=0.6)
    ax.text(DUR - 2, 63, "scale up (60%)", ha="right", fontsize=8, color=ATK, alpha=0.8)
    ax.axhline(25, color="#2a78d6", ls=":", lw=0.9, alpha=0.8)
    ax.text(DUR - 2, 28, "scale down (25%)", ha="right", fontsize=8, color="#2a78d6")
    ax.axvline(BASE_INI, color=MUTED, lw=0.8, ls=":")
    ax.axvline(BASE_FIM, color=MUTED, lw=0.8, ls=":")
    ax.set_ylim(0, max(130, m.average_cpu_percent.max() * 1.1))
    ax2.set_ylim(0, 5)
    ax2.set_yticks([1, 2, 3, 4])
    ax2.set_ylabel("Nº de instâncias", color=INST)
    ax2.tick_params(colors=INST)
    ax.set_xlim(0, DUR)
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("CPU média por instância (%)")
    ax.grid(True, alpha=0.2)
    ax.set_title("(a) CPU e instâncias ao longo do teste", fontsize=11)

    # (b) RTT + faixas de detector
    axr.axvspan(0, BASE_INI, color="#f59e0b", alpha=0.10, lw=0, zorder=0)       # arranque descartado
    axr.axvspan(BASE_INI, BASE_FIM, color="#999999", alpha=0.12, lw=0, zorder=0)  # baseline
    if atacado:
        axr.axvspan(A0, A1, color=ATK, alpha=0.06, lw=0, zorder=0)
    seg = r.groupby((r.t // 1).astype(int)).rtt.mean()
    axr.plot(seg.index + 0.5, seg.values, color="#1f2937", lw=1.3, zorder=3)
    axr.axhline(RAZAO * mu, color="#7a3fd6", lw=1, ls=":")
    axr.text(DUR - 2, RAZAO * mu * 1.25, "1,8× o RTT da baseline", ha="right", fontsize=8, color="#7a3fd6")
    if atacado:
        for x_ in (A0, A1):
            axr.axvline(x_, color=ATK, lw=1, ls="--")
    axr.text((BASE_INI + BASE_FIM) / 2, axr.get_ylim()[1], "baseline", fontsize=8, color=MUTED, ha="center", va="top")
    axr.text(BASE_INI / 2, axr.get_ylim()[1], "arranque", fontsize=6.5, color="#b45309", ha="center", va="top", rotation=90)
    axr.set_yscale("log")
    axr.set_ylim(max(0.3, seg.min() * 0.5), max(50, seg.max() * 1.4))
    axr.set_xlim(0, DUR)
    axr.set_ylabel("RTT médio/s\n(ms, log)")
    axr.grid(True, axis="y", alpha=0.2)
    axr.tick_params(labelbottom=False)
    axr.set_title("(b) RTT e veredito de cada detector a cada 10 s", fontsize=11)

    DETS = [("cusum", "CUSUM c/ reset"), ("z", "Z robusto"), ("ent", "Entropia JS"), ("comb", "Combinado")]
    for k, (col, nome) in enumerate(DETS):
        y = len(DETS) - 1 - k
        axs.barh(y, BASE_FIM, left=0, height=0.8, color="#d1d5db", edgecolor="white")
        for _, row in jan[jan.fim > BASE_FIM].iterrows():
            axs.barh(y, 10, left=row.fim - 10, height=0.8, color=ATK if row[col] else OK,
                     edgecolor="white", linewidth=0.7)
        if atacado:
            txt = f"{int(dentro[col].sum())}/{len(dentro)} ataque · {int(depois[col].sum())}/{len(depois)} depois"
        else:
            tudo = jan[jan.fim > BASE_FIM]
            txt = f"{int(tudo[col].sum())}/{len(tudo)} alarmes falsos"
        axs.text(DUR + 2, y, txt, va="center", fontsize=8, color=INK)
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

    h_leg = [Line2D([0], [0], color=cpu_cor, lw=2, label="CPU média"),
             Line2D([0], [0], color=INST, lw=1.3, ls="--", label="nº de instâncias"),
             Line2D([0], [0], color="#1f2937", lw=1.3, label="RTT médio/s"),
             Patch(color="#f59e0b", alpha=0.3, label="arranque (descartado)"),
             Patch(color="#d1d5db", label="baseline"),
             Patch(color=OK, label="detector: normal"), Patch(color=ATK, label="detector: ataque")]
    fig.legend(handles=h_leg, loc="lower center", bbox_to_anchor=(0.5, 0.075), ncol=7, fontsize=8.2, frameon=False)

    atk_rps = rps * pct / 100
    if atacado:
        titulo = (f"Normal {rps} rps WU={wu_n:,} + ataque {pct}% "
                  f"({atk_rps:g} rps, WU={wu_a:,})").replace(",", ".")
    else:
        titulo = f"Normal isolado {rps} rps, WU={wu_n:,} (sem ataque)".replace(",", ".")
    furtivo = atacado and escalou_atk and not bool(dentro.comb.any())
    if furtivo:
        titulo += "  —  FURTIVO: escalou sem alarme do combinado"
    fig.suptitle(titulo, fontsize=12.5, color=ATK if furtivo else INK)
    fig.text(0.01, 0.01,
             f"Execução: {suf} · tempo 240 s · {'ataque 60-180 s · ' if atacado else ''}baseline = RTT em t∈[15,60) (arranque aparado) · "
             f"erro do tráfego normal: {err_norm:.2f}%  |  combinado com baseline cheio [0,60): {comb_full}/{len(dentro) if atacado else '-'}\n"
             f"Detectores (EntCusumZV3 §143): CUSUM κ=0,5σ h=1000σ com reset · Z robusto (>{100*Z_FRAC_RECOMENDADA:g}% c/ z>{Z_K_RECOMENDADO:g}) · "
             f"entropia Jensen-Shannon (>{ENTROPIA_JS_RECOMENDADO:g}) · combinado: média > 1,8× E (Z OU CUSUM) · tempo do RTT corrigido (§128)",
             fontsize=7.4, color=MUTED, va="bottom")
    fig.subplots_adjust(left=0.05, right=0.90, top=0.90, bottom=0.2)
    nome_a = f"_awu{wu_a}" if atacado else ""
    out = f"{OUT_DIR}/edos_furtivo_agg{rps}_nwu{wu_n}_atk{pct}pct{nome_a}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    nj = len(dentro) if atacado else len(jan[jan.fim > BASE_FIM])
    return dict(rps=rps, wu_n=wu_n, wu_a=wu_a if atacado else 0, pct=pct,
                escalou_atk=escalou_atk, inst_max=int(m.num_instances.max()),
                cpu_pico=round(m.average_cpu_percent.max(), 1), rtt_base_ms=round(mu, 2),
                erro_normal=round(err_norm, 2) if err_norm == err_norm else np.nan,
                cusum=int(dentro.cusum.sum()) if atacado else int(jan[jan.fim > BASE_FIM].cusum.sum()),
                z=int(dentro.z.sum()) if atacado else int(jan[jan.fim > BASE_FIM].z.sum()),
                ent=int(dentro.ent.sum()) if atacado else int(jan[jan.fim > BASE_FIM].ent.sum()),
                comb=int(dentro.comb.sum()) if atacado else int(jan[jan.fim > BASE_FIM].comb.sum()),
                comb_base_cheio=comb_full, n_jan=nj, furtivo=furtivo)


def heatmap(df, col, nome_det, arquivo):
    atk = df[df.pct > 0]
    fig, axes = plt.subplots(len(RPS_LIST), len(WU_NORMAL), figsize=(13, 9))
    fig.subplots_adjust(left=0.08, right=0.88, top=0.88, bottom=0.1, hspace=0.3, wspace=0.2)
    im = None
    for ri, rps in enumerate(RPS_LIST):
        for ci, wu_n in enumerate(WU_NORMAL):
            ax = axes[ri, ci]
            mat = np.full((len(WU_ATAQUE), len(INTENS)), np.nan)
            for i, wu_a in enumerate(WU_ATAQUE):
                for j, p in enumerate(INTENS):
                    c = atk[(atk.rps == rps) & (atk.wu_n == wu_n) & (atk.wu_a == wu_a) & (atk.pct == p)]
                    if len(c):
                        mat[i, j] = 100 * c[col].values[0] / c.n_jan.values[0]
            im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=100, aspect="auto")
            ax.set_xticks(range(len(INTENS)))
            ax.set_xticklabels([f"{p}%" for p in INTENS])
            ax.set_yticks(range(len(WU_ATAQUE)))
            ax.set_yticklabels([f"{wu:,}".replace(",", ".") for wu in WU_ATAQUE])
            ax.set_title(f"normal {rps} rps · WU_normal={wu_n:,}".replace(",", "."), fontsize=10)
            if ri == len(RPS_LIST) - 1:
                ax.set_xlabel("Intensidade do ataque")
            if ci == 0:
                ax.set_ylabel("WU do ataque")
            for i, wu_a in enumerate(WU_ATAQUE):
                for j, p in enumerate(INTENS):
                    c = atk[(atk.rps == rps) & (atk.wu_n == wu_n) & (atk.wu_a == wu_a) & (atk.pct == p)]
                    if not len(c):
                        continue
                    v = mat[i, j]
                    esc = bool(c.escalou_atk.values[0])
                    ax.text(j, i, f"{v:.0f}%\n{int(c[col].values[0])}/{int(c.n_jan.values[0])}",
                            ha="center", va="center", fontsize=7.5,
                            color="white" if v > 55 else INK, fontweight="bold")
                    if esc and v == 0:
                        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=ATK, lw=2.5, zorder=6))
                    elif esc:
                        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                                   edgecolor="#f59e0b", lw=1.5, ls="--", zorder=5))
    cax = fig.add_axes([0.905, 0.32, 0.016, 0.4])
    fig.colorbar(im, cax=cax, label="% das 11 janelas do ataque com alarme")
    fig.legend(handles=[Patch(fc="none", ec=ATK, lw=2.5, label="escalou e 0 alarmes (FURTIVO)"),
                        Patch(fc="none", ec="#f59e0b", lw=1.5, ls="--", label="escalou (com algum alarme)")],
               loc="lower center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle(f"Detecção do EDoS furtivo — {nome_det}\nRPS x WU_normal x WU_ataque x intensidade · "
                 "baseline aparado do arranque · 1 rep", fontsize=12.5)
    out = f"{OUT_DIR}/{arquivo}"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("Salvo:", out)


if __name__ == "__main__":
    if "--heatmap-only" not in sys.argv:
        rows = []
        for rps in RPS_LIST:
            for wu_n in WU_NORMAL:
                r0 = painel(rps, wu_n, None, 0)
                if r0:
                    rows.append(r0)
                for wu_a in WU_ATAQUE:
                    if wu_a <= wu_n:
                        continue
                    for pct in INTENS:
                        rr = painel(rps, wu_n, wu_a, pct)
                        if rr:
                            rows.append(rr)
                            flag = "  *** FURTIVO ***" if rr["furtivo"] else ""
                            print(f"agg{rps} nwu{wu_n} awu{wu_a} atk{pct}%: escalou={rr['escalou_atk']} "
                                  f"inst={rr['inst_max']} cpu={rr['cpu_pico']} base={rr['rtt_base_ms']}ms | "
                                  f"comb {rr['comb']}/{rr['n_jan']} (cheio {rr['comb_base_cheio']}) "
                                  f"cusum {rr['cusum']} z {rr['z']} ent {rr['ent']}{flag}")
        df = pd.DataFrame(rows)
        df.to_csv(f"{D}/resumo_edos_furtivo_wu_rps.csv", index=False)
    else:
        df = pd.read_csv(f"{D}/resumo_edos_furtivo_wu_rps.csv")
    heatmap(df, "comb", "Combinado (média + Z/CUSUM)", "heatmap_furtivo_combinado.png")
    heatmap(df, "cusum", "CUSUM 1000σ com reset", "heatmap_furtivo_cusum.png")
