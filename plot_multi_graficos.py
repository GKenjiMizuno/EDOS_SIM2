"""
Replica dos GRÁFICOS DEFINITIVOS escolhidos (graficos_apresentacao/
graficos_escolhidos.txt) sob o modelo MULTI-ENDPOINT (mistura Sotelo Monge),
a partir das três baterias complementares (run_multi_endpoint_graficos.py):

  D) experiment_results/multi_ataque_isolado/   -> gráfico 27 (isolado × combinado)
  A) experiment_results/multi_clientes_rps/     -> gráficos 11, 17, 20 (invariância por nº de clientes)
  B) experiment_results/multi_normal_log2/      -> gráficos 42, 59/60/61 (curva de capacidade ampla)

O lado COMBINADO do gráfico 27 vem da bateria DEFINITIVA já existente
(experiment_results/edos_multi_endpoint_iso2/, mesma intensidade/RPS, com tráfego
normal). Mistura de endpoints {1000:40% 5000:30% 10000:20% 50000:10%}; ataque só
no maior endpoint (WU=50000); timing ISO2-B (780 s, ataque 300-600 s).

Reusa a maquinaria de detecção/janelas de plot_multi_endpoint_iso2 (detectores
EntCusumZV3, baseline [60,300), combinado = média>1,8× E (Z OU CUSUM)).

Saídas em graficos_apresentacao/multi_endpoint_graficos/.
Uso: python3 plot_multi_graficos.py
"""
import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import plot_multi_endpoint_iso2 as mep

DIR_D = "experiment_results/multi_ataque_isolado"
DIR_A = "experiment_results/multi_clientes_rps"
DIR_B = "experiment_results/multi_normal_log2"
DIR_COMB = "experiment_results/edos_multi_endpoint_iso2"      # combinado (def.) p/ gráfico 27
OUT_DIR = "graficos_apresentacao/multi_endpoint_graficos"
os.makedirs(OUT_DIR, exist_ok=True)

MENU = mep.MENU
MENU_STR = mep.MENU_STR
ATAQUE_WU = mep.ATAQUE_WU
A0, A1, DUR = mep.A0, mep.A1, mep.DUR
BASE_INI, BASE_FIM = mep.BASE_INI, mep.BASE_FIM

RPS_ATK = [160, 240, 320]
INTENS = [1, 5, 10, 15, 20, 25]
REPS5 = [1, 2, 3, 4, 5]
A_CLIENTES = [1, 2, 4, 8, 16]
A_RPS = [160, 240, 320]
A_REPS = [1, 2, 3]
B_RPS = [20, 40, 80, 160, 320, 640, 1280, 2560]
B_REPS = [1, 2, 3]

BLUE, GREEN, ORANGE, RED, PURPLE, GRAY, INST, INK = (
    "#2a78d6", "#1baf7a", "#e08a2b", "#d03b3b", "#7a3fd6", "#888888", "#555555", "#1f2937")
CLIENT_COLOR = {1: "#2a78d6", 2: "#1baf7a", 4: "#e08a2b", 8: "#d03b3b", 16: "#7a3fd6"}
CLIENT_MARK = {1: "o", 2: "s", 4: "^", 8: "D", 16: "v"}


# ----------------------------------------------------------------------------- loaders
def carrega(dirpath, suf):
    """metrics_ + rtt_log_ -> (m, r) com tempo do RTT corrigido (igual mep.carrega)."""
    mp, rp = f"{dirpath}/metrics_{suf}.csv", f"{dirpath}/rtt_log_{suf}.csv"
    if not (os.path.exists(mp) and os.path.exists(rp)):
        return None
    m = pd.read_csv(mp)
    r = pd.read_csv(rp).sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    r = r.assign(t=tt - np.cumsum(np.where(lac > 2, lac, 0)))
    return m, r


def resumo_summary(path):
    """(err_rate %, real_rps agregado, n_workers) de um *_summary_log_*.csv."""
    if not os.path.exists(path):
        return float("nan"), float("nan"), 0
    raw = pd.read_csv(path)
    sdf = raw[raw["total_requests"].notna()]
    ok = sdf["total_requests"].sum()
    err = sdf["errors"].sum()
    real = sdf["real_rps"].sum()
    rate = 100.0 * err / (ok + err) if (ok + err) > 0 else float("nan")
    return rate, real, len(sdf)


def deteccao_run(dirpath, suf):
    """% de janelas do ataque com alarme COMBINADO (e escalou/inst) de 1 run atacado."""
    carga = carrega(dirpath, suf)
    if carga is None:
        return None
    m, r = carga
    _, _, jan = mep.detectores(r)
    mt = mep._metricas(m, jan, atacado=True)
    pct = 100.0 * mt["comb"] / mt["n_jan"] if mt["n_jan"] else np.nan
    return dict(comb_pct=pct, escalou=mt["escalou_atk"], inst_atk=mt["inst_atk"],
                cpu_pico=float(m.average_cpu_percent.max()))


# ----------------------------------------------------------------------------- GRÁFICO 27
def _rtt_janela(dirpath, suf, t0, t1):
    """RTT médio das requisições cujo tempo corrigido cai em [t0,t1). NaN se vazio."""
    carga = carrega(dirpath, suf)
    if carga is None:
        return np.nan
    _, r = carga
    w = r.rtt.values[(r.t.values >= t0) & (r.t.values < t1)]
    return float(w.mean()) if len(w) else np.nan


def _rtt_attack_label(dirpath, suf):
    """RTT médio das requisições rotuladas 'attack' (robusto no isolado esparso,
    onde a correção de ociosidade distorce a grade de tempo). NaN se não houver."""
    mp, rp = f"{dirpath}/metrics_{suf}.csv", f"{dirpath}/rtt_log_{suf}.csv"
    if not os.path.exists(rp):
        return np.nan
    r = pd.read_csv(rp)
    w = r.rtt.values[r.label.values == "attack"]
    return float(w.mean()) if len(w) else np.nan


def grafico_27():
    """Isolado × Combinado — DILUIÇÃO do sinal de RTT pelo tráfego normal.

    A bateria isolada roda o ataque SEM tráfego normal (D=50000): o RTT da janela
    de ataque é o RTT 'puro' do ataque. No combinado, o MESMO ataque entra numa
    janela dominada por milhares de requisições normais rápidas, então a MÉDIA da
    janela mal se mexe. Para cada RPS mostramos, por intensidade, o RTT médio da
    janela de ataque isolado × combinado, contra a baseline normal e o piso de
    detecção (1,8× a baseline) — o isolado cruza o piso (detectável), o combinado
    fica abaixo (furtivo)."""
    suf_iso = lambda rps, pct, rep: f"agg{rps}_isolado_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"
    suf_cmb = lambda rps, pct, rep: f"agg{rps}_mix_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), sharey=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.80, bottom=0.14, wspace=0.08)
    xs = np.arange(len(INTENS))
    for k, rps in enumerate(RPS_ATK):
        ax = axes[k]
        # baseline normal (RTT pré-ataque do run combinado sem ataque)
        base_vals = [_rtt_janela(DIR_COMB, f"agg{rps}_mix_atk0pct_rep{rep}", BASE_INI, BASE_FIM)
                     for rep in REPS5]
        base = float(np.nanmedian(base_vals)) if np.any(~np.isnan(base_vals)) else np.nan
        iso, cmb = [], []
        for pct in INTENS:
            iv = [_rtt_attack_label(DIR_D, suf_iso(rps, pct, rep)) for rep in REPS5]
            cv = [_rtt_janela(DIR_COMB, suf_cmb(rps, pct, rep), A0, A1) for rep in REPS5]
            iso.append(np.nanmedian(iv) if np.any(~np.isnan(iv)) else np.nan)
            cmb.append(np.nanmedian(cv) if np.any(~np.isnan(cv)) else np.nan)
        ax.plot(xs, iso, "o-", color=RED, lw=2, ms=7, label="ataque ISOLADO (RTT puro)")
        ax.plot(xs, cmb, "s-", color=BLUE, lw=2, ms=7, label="COMBINADO (média da janela)")
        if base == base:
            ax.axhline(base, color=GRAY, ls="-", lw=1.1)
            ax.axhline(1.8 * base, color=PURPLE, ls=":", lw=1.3)
            ax.text(len(INTENS) - 1, base * 1.03, "baseline normal", fontsize=7.5,
                    color=GRAY, ha="right", va="bottom")
            ax.text(len(INTENS) - 1, 1.8 * base * 1.03, "piso de detecção (1,8×)", fontsize=7.5,
                    color=PURPLE, ha="right", va="bottom")
        ax.set_yscale("log")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{p}%" for p in INTENS])
        ax.set_xlabel("Intensidade do ataque")
        ax.set_title(f"{rps} rps agregado", fontsize=11)
        ax.grid(True, which="both", alpha=0.2)
        if k == 0:
            ax.set_ylabel("RTT médio da janela de ataque (ms, log)")
            ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("Gráfico 27 (multi-endpoint) — ATAQUE ISOLADO × COMBINADO: diluição do RTT pelo tráfego normal\n"
                 f"mistura {MENU_STR} · ataque só no endpoint WU={ATAQUE_WU:,} · ISO2-B · "
                 "o mesmo ataque é visível isolado e some na média quando diluído no tráfego normal".replace(",", "."),
                 fontsize=12)
    out = f"{OUT_DIR}/27_multi_isolado_vs_combinado.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("Salvo:", out)


# ----------------------------------------------------------------------------- A: tabela clientes×RPS
def tabela_A():
    rows = []
    for rps in A_RPS:
        for clientes in A_CLIENTES:
            cpu_c, errs, reals, maxinst = [], [], [], 0
            peaks = []        # pico pré-escalonamento
            escs = 0
            for rep in A_REPS:
                suf = f"agg{rps}_c{clientes}_mix_rep{rep}"
                mp = f"{DIR_A}/metrics_{suf}.csv"
                if not os.path.exists(mp):
                    continue
                m = pd.read_csv(mp).iloc[1:]
                cpu_c.append(m.average_cpu_percent.mean())
                maxinst = max(maxinst, int(m.num_instances.max()))
                su_idx = m.index[m.decision == "SCALE_UP"]
                escalou = len(su_idx) > 0
                escs += int(escalou)
                pre = m.iloc[:m.index.get_loc(su_idx[0]) + 1] if escalou else m
                peaks.append(pre.average_cpu_percent.max())
                er, rl, _ = resumo_summary(f"{DIR_A}/normal_traffic_summary_log_{suf}.csv")
                if er == er:
                    errs.append(er)
                if rl == rl:
                    reals.append(rl)
            if not cpu_c:
                continue
            rows.append(dict(
                rps=rps, clients=clientes, n=len(cpu_c),
                cpu_mean=stats.mean(cpu_c), cpu_std=stats.stdev(cpu_c) if len(cpu_c) > 1 else 0.0,
                err_mean=stats.mean(errs) if errs else np.nan,
                err_std=stats.stdev(errs) if len(errs) > 1 else 0.0,
                real_mean=stats.mean(reals) if reals else np.nan,
                peak_mean=stats.mean(peaks), peak_std=stats.stdev(peaks) if len(peaks) > 1 else 0.0,
                n_escalou=escs, max_inst=maxinst, peaks=peaks,
                escalou_flags=[True] * escs + [False] * (len(cpu_c) - escs)))
    return pd.DataFrame(rows)


def grafico_11(df):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.2))
    for clientes in A_CLIENTES:
        sub = df[df.clients == clientes].sort_values("rps")
        if sub.empty:
            continue
        ax1.errorbar(sub.rps, sub.cpu_mean, yerr=sub.cpu_std, fmt=f"{CLIENT_MARK[clientes]}-",
                     color=CLIENT_COLOR[clientes], markersize=8, lw=1.8, capsize=4,
                     label=f"{clientes} cliente(s)")
        ax2.errorbar(sub.rps, sub.err_mean, yerr=sub.err_std, fmt=f"{CLIENT_MARK[clientes]}-",
                     color=CLIENT_COLOR[clientes], markersize=8, lw=1.8, capsize=4,
                     label=f"{clientes} cliente(s)")
    ax1.axhline(60, color=RED, ls=":", lw=1, label="limiar SCALE_UP (60%)")
    for ax in (ax1, ax2):
        ax.set_xticks(A_RPS)
        ax.set_xlabel("RPS agregado alvo (mistura de endpoints)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    ax1.set_ylabel("CPU média do container (%) ± desvio")
    ax1.set_title("CPU média por decomposição clientes×RPS\n(pontos do mesmo agregado deveriam coincidir)")
    ax2.set_ylabel("Taxa de erro média (%) ± desvio")
    ax2.set_ylim(0, 1.0)
    ax2.set_title("Taxa de erro por decomposição clientes×RPS (escala fixa 0-1%)")
    fig.suptitle("Gráfico 11 (multi-endpoint) — invariância por nº de clientes (3 reps/ponto)\n"
                 f"tráfego normal = mistura {MENU_STR} · o que importa é o RPS agregado", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out = f"{OUT_DIR}/11_multi_clients_rps_invariancia.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("Salvo:", out)


def grafico_17(df):
    mat = np.full((len(A_RPS), len(A_CLIENTES)), np.nan)
    inst = np.zeros((len(A_RPS), len(A_CLIENTES)), dtype=int)
    for _, r in df.iterrows():
        i, j = A_RPS.index(r.rps), A_CLIENTES.index(r.clients)
        mat[i, j] = r.cpu_mean
        inst[i, j] = int(r.max_inst)
    fig, ax = plt.subplots(figsize=(9.5, 6))
    vmax = np.nanmax(mat)
    im = ax.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=vmax)
    ax.set_xticks(range(len(A_CLIENTES)))
    ax.set_xticklabels([f"{c} cli." for c in A_CLIENTES])
    ax.set_yticks(range(len(A_RPS)))
    ax.set_yticklabels([f"{rps} rps" for rps in A_RPS])
    ax.set_xlabel("nº de clientes (decomposição)")
    ax.set_ylabel("RPS agregado alvo")
    for i, rps in enumerate(A_RPS):
        for j, c in enumerate(A_CLIENTES):
            if np.isnan(mat[i, j]):
                continue
            ax.text(j, i, f"{mat[i, j]:.1f}%\n{rps / c:g} rps/cli\nmáx {inst[i, j]} inst.",
                    ha="center", va="center", fontsize=8.5,
                    color="white" if mat[i, j] > vmax * 0.6 else "black")
    fig.colorbar(im, ax=ax, label="CPU média do container (%)")
    ax.set_title("Gráfico 17 (multi-endpoint) — grid clientes×RPS, CPU média por célula\n"
                 "cada LINHA (mesmo agregado) deveria ficar com cor uniforme")
    fig.tight_layout()
    out = f"{OUT_DIR}/17_multi_grid_heatmap_cpu.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("Salvo:", out)


def grafico_20(df):
    fig, ax = plt.subplots(figsize=(11, 6.5))
    import random
    random.seed(0)
    for _, r in df.iterrows():
        col = CLIENT_COLOR[r.clients]
        escf = r.escalou_flags
        for k, peak in enumerate(r.peaks):
            jit = r.rps * random.uniform(-0.02, 0.02)
            if k < len(escf) and escf[k]:
                ax.scatter(r.rps + jit, peak, color=col, s=55, zorder=4, edgecolors="white", linewidths=0.7)
            else:
                ax.scatter(r.rps + jit, peak, facecolors="none", edgecolors=col, s=55, zorder=4,
                           linewidths=1.3, alpha=0.6)
    for clientes in A_CLIENTES:
        sub = df[df.clients == clientes].sort_values("rps")
        if sub.empty:
            continue
        ax.errorbar(sub.rps, sub.peak_mean, yerr=sub.peak_std, fmt="-", color=CLIENT_COLOR[clientes],
                    lw=1.8, capsize=4, zorder=3, label=f"{clientes} cliente(s)")
    ax.axhline(60, color=RED, ls="--", lw=1, label="limiar SCALE_UP (60%)")
    ax.set_xticks(A_RPS)
    ax.set_xlabel("RPS agregado alvo (mistura de endpoints)")
    ax.set_ylabel("CPU de pico — só a janela com 1 instância (%)")
    ax.set_title("Gráfico 20 (multi-endpoint) — capacidade de 1 instância\n"
                 "pico ANTES do primeiro escalonamento (mesmos dados do 17)")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = f"{OUT_DIR}/20_multi_pico_pre_escalonamento.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("Salvo:", out)


# ----------------------------------------------------------------------------- B: curva ampla log2
def tabela_B():
    rows, raw = [], []
    for agg in B_RPS:
        peaks, means, pres, maxinst, escs, reals = [], [], [], 0, 0, []
        for rep in B_REPS:
            suf = f"agg{agg}_mix_rep{rep}"
            mp = f"{DIR_B}/metrics_{suf}.csv"
            if not os.path.exists(mp):
                continue
            m = pd.read_csv(mp).iloc[1:]
            peak = m.average_cpu_percent.max()
            su_idx = m.index[m.decision == "SCALE_UP"]
            escalou = len(su_idx) > 0
            pre = m.iloc[:m.index.get_loc(su_idx[0]) + 1] if escalou else m
            peaks.append(peak)
            means.append(m.average_cpu_percent.mean())
            pres.append(pre.average_cpu_percent.max())
            maxinst = max(maxinst, int(m.num_instances.max()))
            escs += int(escalou)
            raw.append((agg, peak, escalou))
            _, rl, _ = resumo_summary(f"{DIR_B}/normal_traffic_summary_log_{suf}.csv")
            if rl == rl:
                reals.append(rl)
        if not peaks:
            continue
        rows.append(dict(aggr=agg, n=len(peaks),
                         peak_mean=stats.mean(peaks), peak_std=stats.stdev(peaks) if len(peaks) > 1 else 0.0,
                         peak_max=max(peaks), peaks=peaks,
                         mean_mean=stats.mean(means), mean_std=stats.stdev(means) if len(means) > 1 else 0.0,
                         pre_mean=stats.mean(pres), pre_std=stats.stdev(pres) if len(pres) > 1 else 0.0,
                         n_escalou=escs, max_inst=maxinst,
                         real_mean=stats.mean(reals) if reals else np.nan))
    return pd.DataFrame(rows), raw


def grafico_42(df, raw):
    fig, ax = plt.subplots(figsize=(12, 7))
    aggs = [a for a in B_RPS if a in set(df['aggr'])]
    box_data = [df[df['aggr'] == a].peaks.values[0] for a in aggs]
    bp = ax.boxplot(box_data, positions=aggs, widths=[a * 0.22 for a in aggs],
                    showfliers=False, patch_artist=True, zorder=2, manage_ticks=False)
    for patch in bp["boxes"]:
        patch.set_facecolor("#f0c419")
        patch.set_alpha(0.25)
        patch.set_edgecolor("#b8930f")
    for el in ("whiskers", "caps", "medians"):
        for ln in bp[el]:
            ln.set_color("#b8930f")
            ln.set_linewidth(1.3)
    import random
    random.seed(0)
    for agg, peak, escalou in raw:
        jit = 2 ** random.uniform(-0.04, 0.04)
        if escalou:
            ax.scatter(agg * jit, peak, color=GREEN, s=70, zorder=4, edgecolors="white", linewidths=0.8)
        else:
            ax.scatter(agg * jit, peak, facecolors="none", edgecolors=GRAY, s=70, zorder=4, linewidths=1.5)
    ax.errorbar(df['aggr'], df.peak_mean, yerr=df.peak_std, fmt="-", color=BLUE, lw=1.6, capsize=5,
                zorder=2.8, alpha=0.75, label="CPU de pico (média ± desvio)")
    ax.axhline(60, color=RED, ls="--", lw=1, label="limiar SCALE_UP (60%)", zorder=1.5)
    for _, r in df.iterrows():
        ax.annotate(f"{r.n_escalou}/{r.n} escalou", xy=(r['aggr'], r.peak_max), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=7.5, color="#333")
    ax.set_xscale("log", base=2)
    ax.set_xticks(B_RPS)
    ax.set_xticklabels([str(a) for a in B_RPS])
    ax.set_xlim(15, 3600)
    handles, labels = ax.get_legend_handles_labels()
    handles += [Patch(facecolor="#f0c419", alpha=0.25, edgecolor="#b8930f", label="caixa = Q1-Q3, linha = mediana"),
                Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=9,
                       markeredgecolor="white", label="repetição que ESCALOU"),
                Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor=GRAY,
                       markersize=9, markeredgewidth=1.5, label="repetição que NÃO escalou")]
    ax.set_xlabel("RPS agregado (tráfego normal, mistura de endpoints, escala log2)")
    ax.set_ylabel("CPU de pico (%)")
    ax.set_title("Gráfico 42 (multi-endpoint) — curva de capacidade, potência de 2 base 20, com quartis\n"
                 f"mistura {MENU_STR} · 3 reps por agregado")
    ax.legend(handles=handles, loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = f"{OUT_DIR}/42_multi_curva_capacidade_pow2.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("Salvo:", out)


def grafico_60(df):
    graficos = [("mean_mean", "mean_std", "59_multi_normal_cpu_media.png",
                 "CPU média do run (%)", "CPU média"),
                ("peak_mean", "peak_std", "60_multi_normal_cpu_pico.png",
                 "CPU de pico do run (%)", "CPU de pico"),
                ("pre_mean", "pre_std", "61_multi_normal_pico_pre_escalonamento.png",
                 "CPU de pico antes do 1º SCALE_UP (%)", "Pico pré-escalonamento (capacidade de 1 instância)")]
    for col, colsd, fname, ylabel, titulo in graficos:
        fig, ax = plt.subplots(figsize=(11, 6.5))
        ax.errorbar(df['aggr'], df[col], yerr=df[colsd], fmt="-", color=BLUE, lw=2, capsize=4, zorder=2)
        for _, r in df.iterrows():
            escalou = r.n_escalou > 0
            if escalou:
                ax.scatter(r['aggr'], r[col], s=80, color=BLUE, edgecolors="white", linewidths=1, zorder=4)
            else:
                ax.scatter(r['aggr'], r[col], s=80, facecolors="white", edgecolors=BLUE, linewidths=2, zorder=4)
            teto = not np.isnan(r.real_mean) and r.real_mean < 0.8 * r['aggr']
            if teto:
                ax.scatter(r['aggr'], r[col], s=260, facecolors="none", edgecolors=RED, linewidths=1.8, zorder=3)
            real_txt = f"real {r.real_mean:.0f} rps" if not np.isnan(r.real_mean) else "real ?"
            ax.annotate(f"{r[col]:.0f}%\n{r.max_inst} inst.\n{real_txt}", xy=(r['aggr'], r[col]),
                        xytext=(0, 12), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, color=RED if teto else "#333333")
        ax.axhline(60, color=RED, ls="--", lw=1, zorder=1)
        ax.set_xscale("log", base=2)
        ax.set_xticks(B_RPS)
        ax.set_xticklabels([str(a) for a in B_RPS])
        ax.set_xlim(14, 3600)
        ax.set_ylim(0, max(100, df[col].max() * 1.35))
        ax.set_xlabel("RPS agregado nominal (mistura de endpoints, 4 clientes, escala log2)")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{titulo} — tráfego normal multi-endpoint\n3 reps por agregado (média ± desvio)", fontsize=11.5)
        ax.grid(True, alpha=0.3)
        ax.legend(handles=[Line2D([0], [0], color=RED, ls="--", lw=1, label="limiar SCALE_UP (60%)"),
                           Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=9,
                                  label="escalou (≥1 SCALE_UP)"),
                           Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
                                  markeredgecolor=BLUE, markeredgewidth=2, markersize=9, label="não escalou"),
                           Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
                                  markeredgecolor=RED, markeredgewidth=1.8, markersize=14,
                                  label="teto do gerador do cliente (real < 80% nominal)")],
                  loc="upper left", fontsize=8.5)
        fig.tight_layout()
        out = f"{OUT_DIR}/{fname}"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print("Salvo:", out)


if __name__ == "__main__":
    print("== Gráfico 27 (isolado × combinado) ==")
    grafico_27()
    print("== Gráficos 11/17/20 (clientes × RPS) ==")
    dfa = tabela_A()
    dfa.drop(columns=["peaks", "escalou_flags"]).to_csv(f"{OUT_DIR}/resumo_A_clientes_rps.csv", index=False)
    grafico_11(dfa)
    grafico_17(dfa)
    grafico_20(dfa)
    print("== Gráficos 42/59/60/61 (curva ampla log2) ==")
    dfb, rawb = tabela_B()
    dfb.drop(columns=["peaks"]).to_csv(f"{OUT_DIR}/resumo_B_log2.csv", index=False)
    grafico_42(dfb, rawb)
    grafico_60(dfb)
    print("\nConcluído. Saídas em", OUT_DIR)
