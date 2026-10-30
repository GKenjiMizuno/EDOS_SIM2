"""
Gráficos da bateria MULTI-ENDPOINT (modelo Sotelo Monge 2017 / EDiSON) — timing
ISO2-B. Mesmo desenho dos painéis de plot_edos_furtivo_robusto_iso2 (painel a:
CPU+instâncias; painel b: RTT médio/s + veredito de cada detector), adaptado:
  - tráfego normal = MISTURA de endpoints {1000:40% 5000:30% 10000:20% 50000:10%}
    (WU_n efetivo ~8900), ataque concentrado só no maior endpoint (WU=50000);
  - timing ISO2-B: 780 s, ataque 300-600 s (5 min), baseline aparado t∈[60,300).

Grade: agg {160,320} rps × intensidade {1,5,10,15,20,25}% + baseline 0% × 3 reps.

Saídas em graficos_apresentacao/edos_multi_endpoint_iso2/:
  - um painel por teste (todas as reps);
  - 2 heatmaps (Combinado e CUSUM): RPS × intensidade, valor = MEDIANA das 3 reps
    (% das janelas do ataque com alarme), moldura nas furtivas (frota↑ e 0 alarmes).

Uso: python3 plot_multi_endpoint_iso2.py [--heatmap-only]
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

D = "experiment_results/edos_multi_endpoint_iso2"
OUT_DIR = "graficos_apresentacao/edos_multi_endpoint_iso2"
os.makedirs(OUT_DIR, exist_ok=True)
RPS_LIST = [160, 240, 320]
INTENS = [1, 5, 10, 15, 20, 25]
REPS = [1, 2, 3]
MENU = [(1000, 0.40), (5000, 0.30), (10000, 0.20), (50000, 0.10)]
ATAQUE_WU = max(c for c, _ in MENU)       # ataque só no maior endpoint
WU_N_EFETIVO = int(round(sum(c * p for c, p in MENU)))
A0, A1, DUR = 300, 600, 780               # ISO2-B: ataque 300-600 (5 min)
BASE_INI, BASE_FIM = 60, 300              # baseline aparado do arranque
H, RAZAO = 1000.0, 1.8
ATK, INST, OK, INK, MUTED = "#d03b3b", "#555555", "#1baf7a", "#1f2937", "#6b7280"

MENU_STR = " ".join(f"{c:,}".replace(",", ".") + f":{int(p*100)}%" for c, p in MENU)


def suf_de(rps, pct, rep):
    if pct == 0:
        return f"agg{rps}_mix_atk0pct_rep{rep}"
    return f"agg{rps}_mix_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"


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
    c = 0.0
    disp = np.zeros(len(v), dtype=bool)
    for i, x in enumerate(v):
        c = max(0.0, c + (x - mu) - 0.5 * sd)
        if c > H * sd:
            disp[i] = True
            c = 0.0
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
    return mu, sd, pd.DataFrame(jan)


def _metricas(m, jan, atacado):
    dentro = jan[(jan.fim - 20 >= A0) & (jan.fim <= A1)]
    depois = jan[jan.fim - 20 >= A1]
    escalou_atk = bool(((m.decision == "SCALE_UP") & (m.elapsed_time_s > A0) & (m.elapsed_time_s <= A1)).any())
    jm = (m.elapsed_time_s >= A0) & (m.elapsed_time_s < A1)
    inst_atk = float(m.num_instances[jm].mean()) if jm.any() else np.nan
    tudo = jan[jan.fim > BASE_FIM]
    def cnt(col):
        return int(dentro[col].sum()) if atacado else int(tudo[col].sum())
    nj = len(dentro) if atacado else len(tudo)
    return dict(escalou_atk=escalou_atk, inst_atk=inst_atk, n_jan=nj,
                cusum=cnt("cusum"), z=cnt("z"), ent=cnt("ent"), comb=cnt("comb"),
                dentro=dentro, depois=depois)


def coleta(rps, pct, rep):
    carga = carrega(suf_de(rps, pct, rep))
    if carga is None:
        return None
    m, r = carga
    _, _, jan = detectores(r)
    mt = _metricas(m, jan, pct > 0)
    mt.update(rps=rps, pct=pct, rep=rep,
              inst_max=int(m.num_instances.max()), cpu_pico=round(m.average_cpu_percent.max(), 1))
    return mt


def painel(rps, pct, rep):
    suf = suf_de(rps, pct, rep)
    carga = carrega(suf)
    if carga is None:
        print("[faltando]", suf)
        return None
    m, r = carga
    mu, sd, jan = detectores(r)
    atacado = pct > 0
    mt = _metricas(m, jan, atacado)
    dentro, depois = mt["dentro"], mt["depois"]
    try:
        ns = pd.read_csv(f"{D}/normal_traffic_summary_log_{suf}.csv")
        ns = ns[ns.total_requests.notna()]
        err_norm = 100 * ns.errors.sum() / ns.total_requests.sum()
    except (FileNotFoundError, ZeroDivisionError):
        err_norm = np.nan
    _, _, jan_full = detectores(r, base_ini=0)
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

    axr.axvspan(0, BASE_INI, color="#f59e0b", alpha=0.10, lw=0, zorder=0)
    axr.axvspan(BASE_INI, BASE_FIM, color="#999999", alpha=0.12, lw=0, zorder=0)
    if atacado:
        axr.axvspan(A0, A1, color=ATK, alpha=0.06, lw=0, zorder=0)
    seg = r.groupby((r.t // 1).astype(int)).rtt.mean()
    axr.plot(seg.index + 0.5, seg.values, color="#1f2937", lw=1.0, zorder=3)
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

    h_leg = [Line2D([0], [0], color=cpu_cor, lw=2, label="CPU média"),
             Line2D([0], [0], color=INST, lw=1.3, ls="--", label="nº de instâncias"),
             Line2D([0], [0], color="#1f2937", lw=1.3, label="RTT médio/s"),
             Patch(color="#f59e0b", alpha=0.3, label="arranque (descartado)"),
             Patch(color="#d1d5db", label="baseline"),
             Patch(color=OK, label="detector: normal"), Patch(color=ATK, label="detector: ataque")]
    fig.legend(handles=h_leg, loc="lower center", bbox_to_anchor=(0.5, 0.075), ncol=7, fontsize=8.2, frameon=False)

    atk_rps = rps * pct / 100
    if atacado:
        titulo = (f"Normal {rps} rps (mix {MENU_STR}) + ataque {pct}% "
                  f"({atk_rps:g} rps, WU={ATAQUE_WU:,})").replace(",", ".")
    else:
        titulo = f"Normal isolado {rps} rps (mix {MENU_STR}) — sem ataque"
    furtivo = atacado and mt["escalou_atk"] and not bool(dentro.comb.any())
    if furtivo:
        titulo += "  —  FURTIVO: escalou sem alarme do combinado"
    fig.suptitle(titulo + f"   [rep{rep}]", fontsize=12, color=ATK if furtivo else INK)
    fig.text(0.01, 0.01,
             f"Execução: {suf} · tempo {DUR} s · {f'ataque {A0}-{A1} s · ' if atacado else ''}"
             f"baseline = RTT em t∈[{BASE_INI},{BASE_FIM}) (arranque aparado) · WU_n efetivo ~{WU_N_EFETIVO:,} · "
             f"erro do tráfego normal: {err_norm:.2f}%  |  combinado com baseline cheio [0,{BASE_FIM}): "
             f"{comb_full}/{len(dentro) if atacado else '-'} · instâncias médias no ataque: {mt['inst_atk']:.2f}\n"
             f"Detectores (EntCusumZV3 §143): CUSUM κ=0,5σ h=1000σ com reset · Z robusto (>{100*Z_FRAC_RECOMENDADA:g}% c/ z>{Z_K_RECOMENDADO:g}) · "
             f"entropia Jensen-Shannon (>{ENTROPIA_JS_RECOMENDADO:g}) · combinado: média > 1,8× E (Z OU CUSUM) · tempo do RTT corrigido (§128)".replace(",", "."),
             fontsize=7.4, color=MUTED, va="bottom")
    fig.subplots_adjust(left=0.05, right=0.90, top=0.90, bottom=0.2)
    nome_a = f"_awu{ATAQUE_WU}" if atacado else ""
    out = f"{OUT_DIR}/edos_multi_agg{rps}_mix_atk{pct}pct{nome_a}_rep{rep}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    mt.update(rps=rps, pct=pct, rep=rep)
    return mt


def heatmap(df, col, nome_det, arquivo):
    """df = tabela AGREGADA por célula (mediana das reps). Linhas = RPS, colunas = intensidade."""
    atk = df[df.pct > 0]
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    fig.subplots_adjust(left=0.13, right=0.86, top=0.80, bottom=0.17)
    mat = np.full((len(RPS_LIST), len(INTENS)), np.nan)
    for i, rps in enumerate(RPS_LIST):
        for j, p in enumerate(INTENS):
            c = atk[(atk.rps == rps) & (atk.pct == p)]
            if len(c):
                mat[i, j] = 100 * c[col].values[0] / c.n_jan.values[0]
    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(INTENS)))
    ax.set_xticklabels([f"{p}%" for p in INTENS], fontsize=10)
    ax.set_yticks(range(len(RPS_LIST)))
    ax.set_yticklabels([f"{rps} rps" for rps in RPS_LIST], fontsize=10)
    ax.set_xlabel("Intensidade do ataque")
    ax.set_ylabel("RPS agregado normal")
    for i, rps in enumerate(RPS_LIST):
        for j, p in enumerate(INTENS):
            c = atk[(atk.rps == rps) & (atk.pct == p)]
            if not len(c):
                continue
            v = mat[i, j]
            dan = bool(c.danoso.values[0])
            ax.text(j, i, f"{v:.0f}%\n{int(round(c[col].values[0]))}/{int(c.n_jan.values[0])}",
                    ha="center", va="center", fontsize=8, color="white" if v > 55 else INK, fontweight="bold")
            if dan and v == 0:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=ATK, lw=2.5, zorder=6))
            elif dan:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                           edgecolor="#f59e0b", lw=1.5, ls="--", zorder=5))
    cax = fig.add_axes([0.875, 0.25, 0.018, 0.5])
    fig.colorbar(im, cax=cax, label="% das janelas do ataque com alarme (mediana 3 reps)")
    fig.legend(handles=[Patch(fc="none", ec=ATK, lw=2.5, label="frota↑ e 0 alarmes  (FURTIVO + DANOSO)"),
                        Patch(fc="none", ec="#f59e0b", lw=1.5, ls="--", label="danoso (com algum alarme)")],
               loc="lower center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.suptitle(f"Detecção do EDoS multi-endpoint (ISO2-B) — {nome_det}\n"
                 f"tráfego normal = mix {MENU_STR} · ataque só no endpoint WU={ATAQUE_WU:,} · "
                 "baseline estável [60,300) · mediana de 3 reps · moldura = dano sustentado (Δinst ≥ 0,5)".replace(",", "."),
                 fontsize=11)
    out = f"{OUT_DIR}/{arquivo}"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("Salvo:", out)


DANO_MIN = 0.5


def agrega(df):
    g = df.groupby(["rps", "pct"]).agg(
        comb=("comb", "median"), cusum=("cusum", "median"), z=("z", "median"), ent=("ent", "median"),
        n_jan=("n_jan", "median"), inst_atk=("inst_atk", "median"),
        escalou_maioria=("escalou_atk", lambda s: int(s.sum()) >= 2),
    ).reset_index()
    base_inst = g[g.pct == 0].set_index("rps").inst_atk
    g["base_inst"] = g.rps.map(base_inst)
    g["delta_inst"] = g.inst_atk - g.base_inst
    g["danoso"] = g.delta_inst >= DANO_MIN
    return g


if __name__ == "__main__":
    heatmap_only = "--heatmap-only" in sys.argv
    rows = []
    for rps in RPS_LIST:
        for rep in REPS:
            r0 = coleta(rps, 0, rep) if heatmap_only else painel(rps, 0, rep)
            if r0:
                rows.append({k: r0[k] for k in ("rps", "pct", "rep", "escalou_atk",
                                                "inst_atk", "n_jan", "cusum", "z", "ent", "comb")})
            for pct in INTENS:
                rr = coleta(rps, pct, rep) if heatmap_only else painel(rps, pct, rep)
                if rr:
                    rows.append({k: rr[k] for k in ("rps", "pct", "rep", "escalou_atk",
                                                    "inst_atk", "n_jan", "cusum", "z", "ent", "comb")})
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT_DIR}/resumo_por_rep.csv", index=False)
    g = agrega(df)
    g.to_csv(f"{OUT_DIR}/resumo_mediana.csv", index=False)
    n_pain = len([f for f in os.listdir(OUT_DIR) if f.startswith("edos_multi_agg")])
    print(f"\nPainéis: {n_pain} | células agregadas: {len(g)} | reps por célula: {sorted(df.rep.unique())}")
    heatmap(g, "comb", "Combinado (média + Z/CUSUM)", "heatmap_multi_iso2_combinado.png")
    heatmap(g, "cusum", "CUSUM 1000σ com reset", "heatmap_multi_iso2_cusum.png")
