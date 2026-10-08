"""
Extração para a reavaliação da detecção estatística pós load balancer
(PLANO_DETECCAO_POS_LB.txt, changes.txt §117).

Para cada execução das famílias do plano:
  - roda uma reimplementação FIEL do detector de EntCusumZV3.analisar_
    bursts_tunavel (mesma ordem de operações), mas sem I/O de xlsx/png e
    guardando as estatísticas BRUTAS de cada janela (média/baseline, max Z,
    CUSUM/σ, ΔH), para que qualquer limiar possa ser reaplicado depois;
  - coleta metadados/covariáveis da execução (família, configuração, carga
    real normal/ataque dos summary logs, WU, dano = SCALE_UP, timeouts).

Saídas em experiment_results/deteccao_pos_lb/: runs.csv, windows.csv.gz.

Uso:
  python3 deteccao_pos_lb_extract.py --validar   # confere contra o original
  python3 deteccao_pos_lb_extract.py             # extração completa
  python3 deteccao_pos_lb_extract.py --window 30 # sensibilidade de janela
"""
import argparse
import glob
import os
import re
import shutil
import tempfile
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import stats

import config

OUT_DIR = "experiment_results/deteccao_pos_lb"
ER = "experiment_results"
MIN_SAMPLES = 10


# ---------------------------------------------------------------------------
# Detector -- reimplementação fiel de EntCusumZV3.analisar_bursts_tunavel
# ---------------------------------------------------------------------------
def detector_janelas(rtt_path, window_seconds=20, overlap_percent=50):
    df = pd.read_csv(rtt_path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["tempo_rel"] = df["timestamp"] - df["timestamp"].min()
    vals = df["rtt"].values
    tempo = df["tempo_rel"].values
    stride = window_seconds * (1 - overlap_percent / 100)

    baseline = df.loc[df["tempo_rel"] < config.ATTACK_START_TIME_SECONDS, "rtt"]
    if len(baseline) >= 10:
        mu, sd, n_base, base_ok = baseline.mean(), baseline.std(), len(baseline), True
    else:
        mu, sd, n_base, base_ok = df["rtt"].mean(), df["rtt"].std(), len(baseline), False
    kappa = 0.5 * sd

    cus = np.empty(len(vals))
    c = 0.0
    for i, v in enumerate(vals):
        c = max(0.0, c + (v - mu) - kappa)
        cus[i] = c

    vmin, vmax = vals.min(), vals.max()
    tmax = tempo.max()

    rows = []
    prev = None
    ent_prev = None
    t0 = 0.0
    while t0 < tmax:
        t1 = t0 + window_seconds
        m = (tempo >= t0) & (tempo < t1)
        n = int(m.sum())
        if n < MIN_SAMPLES:
            rows.append(dict(t0=t0, n=n, avaliada=False))
            t0 += stride
            continue
        w = vals[m]
        mean = w.mean()
        std = w.std(ddof=1)
        hist, _ = np.histogram(w, bins=10, range=(vmin, vmax), density=True)
        probs = hist / np.sum(hist) if np.sum(hist) > 0 else np.zeros(10)
        ent = stats.entropy(probs[probs > 0], base=2) if np.any(probs > 0) else 0.0
        dH = abs(ent - ent_prev) if ent_prev is not None else 0.0
        ent_prev = ent
        max_z = 0.0
        if prev and prev["std"] > 0:
            max_z = float(np.max(np.abs((w - prev["mean"]) / prev["std"])))
        cusum = cus[np.where(m)[0][-1]]
        rows.append(dict(t0=t0, n=n, avaliada=True, mean=mean, std=std, entropia=ent,
                         dH=dH, max_z=max_z, cusum=cusum))
        prev = {"mean": mean, "std": std}
        t0 += stride

    out = pd.DataFrame(rows)
    out["base_mean"] = mu
    out["base_std"] = sd
    out["n_base"] = n_base
    out["base_ok"] = base_ok
    out["ratio"] = out["mean"] / mu
    out["cusum_sd"] = out["cusum"] / sd if sd > 0 else np.nan
    return out


def status_original(win, z=3.5, ratio=1.8, h=5.0):
    """Decisão 'DDoS Burst' do EntCusumZV3 original, sobre as janelas avaliadas."""
    w = win[win.avaliada]
    alarm_z = w.max_z > z
    alarm_c = w.cusum > h * w.base_std
    return ((w["mean"] > ratio * w.base_mean) & (alarm_z | alarm_c)).values


# ---------------------------------------------------------------------------
# Catálogo de execuções
# ---------------------------------------------------------------------------
WEDOS_NORMAL = {"S1": 40, "S2": 100, "S3": 200, "S4": 300}
ATK_NORMAL = {"S1": 40, "S2": 100, "S3": 200, "S4": 300, "S5": 20, "S6": 80, "S7": 160,
              "S8": 320, "S9": 640, "S10": 1280, "S11": 2560}

RX = {
    "wedos_grid": re.compile(r"^(S\d+)_atk([\d.]+)pct_wu(\d+)_(.+)_rep(\d+)$"),
    "combined_sweep": re.compile(r"^(S\d+)_atk([\d.]+)pct_wu(\d+)_rep(\d+)$"),
    "atacantes_intensidade_grid": re.compile(r"^(S\d+)_atk([\d.]+)pct_att(\d+)_wu(\d+)_rep(\d+)$"),
    "desempate_combinado_isolado": re.compile(r"^(combinado|isolado)_rps([\d.]+)_att(\d+)_WU(\d+)_rep(\d+)$"),
    "clients_rps_grid": re.compile(r"^agg(\d+)_clients(\d+)_WU(\d+)_rep(\d+)$"),
    "normal_isolado_pos_lb": re.compile(r"^agg(\d+)_WU(\d+)_rep(\d+)$"),
}
NB_RX = [
    (re.compile(r"^normal_agg(\d+)_WU(\d+)_refined_rep(\d+)$"), "refined"),
    (re.compile(r"^normal_rps([\d.]+)_WU(\d+)_thr_agg(\d+)_rep(\d+)$"), "thr"),
    (re.compile(r"^normal_rps75_WU10_repro_lote([AB])_rep(\d+)$"), "repro"),
    (re.compile(r"^normal_rps([\d.]+)_WU(\d+)_rep(\d+)$"), "plain_rep"),
    (re.compile(r"^normal_rps([\d.]+)_WU(\d+)$"), "plain"),
]


def parse_run(fam, suffix):
    """Retorna dict de metadados nominais ou None (fora do escopo)."""
    if fam == "normal_baseline":
        for rx, kind in NB_RX:
            m = rx.match(suffix)
            if not m:
                continue
            g = m.groups()
            if kind == "refined":
                return dict(ataque=False, cenario=f"agg{g[0]}", normal_nom=int(g[0]), normal_wu=int(g[1]),
                            rep=int(g[2]), config=f"nb_agg{g[0]}_wu{g[1]}")
            if kind == "thr":
                return dict(ataque=False, cenario=f"agg{g[2]}", normal_nom=float(g[0]) * 4, normal_wu=int(g[1]),
                            rep=int(g[3]), config=f"nb_thr{g[2]}")
            if kind == "repro":
                return dict(ataque=False, cenario="agg300", normal_nom=300, normal_wu=10,
                            rep=int(g[1]), config=f"nb_repro{g[0]}")
            if kind == "plain_rep":
                return dict(ataque=False, cenario=f"rps{g[0]}", normal_nom=float(g[0]) * 4, normal_wu=int(g[1]),
                            rep=int(g[2]), config=f"nb_rps{g[0]}_wu{g[1]}")
            return dict(ataque=False, cenario=f"rps{g[0]}", normal_nom=float(g[0]) * 4, normal_wu=int(g[1]),
                        rep=1, config=f"nb_rps{g[0]}_wu{g[1]}")
        return None
    m = RX[fam].match(suffix)
    if not m:
        return None
    g = m.groups()
    if fam == "wedos_grid":
        return dict(ataque=True, cenario=g[0], normal_nom=WEDOS_NORMAL[g[0]], normal_wu=10, pct=float(g[1]),
                    atk_wu=int(g[2]), atacantes=4, tag=g[3], rep=int(g[4]),
                    config=f"wg_{g[0]}_{g[1]}_{g[2]}")
    if fam == "combined_sweep":
        return dict(ataque=True, cenario=g[0], normal_nom=WEDOS_NORMAL[g[0]], normal_wu=10, pct=float(g[1]),
                    atk_wu=int(g[2]), atacantes=4, rep=int(g[3]), config=f"cs_{g[0]}_{g[1]}_{g[2]}")
    if fam == "atacantes_intensidade_grid":
        return dict(ataque=True, cenario=g[0], normal_nom=ATK_NORMAL[g[0]], normal_wu=10, pct=float(g[1]),
                    atacantes=int(g[2]), atk_wu=int(g[3]), rep=int(g[4]),
                    config=f"ai_{g[0]}_{g[1]}_{g[2]}", gil=g[0] in ("S9", "S10", "S11"))
    if fam == "desempate_combinado_isolado":
        if g[0] != "combinado":
            return None  # isolado: sem baseline pré-ataque (plano §2)
        return dict(ataque=True, cenario="D40", normal_nom=40, normal_wu=10, rps_atacante=float(g[1]),
                    atacantes=int(g[2]), atk_wu=int(g[3]), rep=int(g[4]),
                    config=f"de_{g[1]}_{g[3]}")
    if fam == "clients_rps_grid":
        return dict(ataque=False, cenario=f"agg{g[0]}", normal_nom=int(g[0]), clientes=int(g[1]),
                    normal_wu=int(g[2]), rep=int(g[3]), config=f"cr_{g[0]}_{g[1]}")
    if fam == "normal_isolado_pos_lb":
        return dict(ataque=False, cenario=f"agg{g[0]}", normal_nom=int(g[0]), normal_wu=int(g[1]),
                    rep=int(g[2]), config=f"np_{g[0]}")
    return None


def summary(path):
    if not path or not os.path.exists(path):
        return np.nan, np.nan, np.nan
    d = pd.read_csv(path)
    d = d[d["total_requests"].notna()]
    if not len(d):
        return np.nan, np.nan, np.nan
    return d["real_rps"].sum(), d["total_requests"].sum(), d["errors"].sum()


def first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


FAMILIAS = ["wedos_grid", "combined_sweep", "atacantes_intensidade_grid",
            "desempate_combinado_isolado", "clients_rps_grid", "normal_baseline",
            "normal_isolado_pos_lb"]


def catalog(base=ER, familias=FAMILIAS):
    runs = []
    for fam in familias:
        for mf in sorted(glob.glob(f"{base}/{fam}/metrics_*.csv")):
            suffix = os.path.basename(mf)[len("metrics_"):-len(".csv")]
            meta = parse_run(fam, suffix)
            if meta is None:
                continue
            d = f"{base}/{fam}"
            tc = f"{d}/traffic_capture_{suffix}.csv"
            meta["captura"] = os.path.exists(tc) and os.path.getsize(tc) > 200
            rtt = first_existing(f"{d}/rtt_log_{suffix}.csv")
            if rtt is None:
                continue
            short = suffix[len("normal_"):] if suffix.startswith("normal_") else suffix
            meta.update(dict(
                familia=fam, suffix=suffix, rtt_path=rtt, metrics_path=mf,
                normal_summary=first_existing(f"{d}/normal_traffic_summary_log_{suffix}.csv",
                                              f"{d}/normal_traffic_summary_log_{short}.csv"),
                attack_summary=first_existing(f"{d}/attack_summary_log_{suffix}.csv"),
            ))
            runs.append(meta)
    return runs


def process(meta, window_seconds=20):
    try:
        win = detector_janelas(meta["rtt_path"], window_seconds=window_seconds)
    except Exception as e:  # registra e segue -- não esconde
        return dict(meta, erro=str(e)), None
    m = pd.read_csv(meta["metrics_path"])
    atk_rows = m[m["label"] == "attack"]
    if len(atk_rows):
        a0 = atk_rows["elapsed_time_s"].min() - config.MONITOR_INTERVAL_SECONDS
        a1 = atk_rows["elapsed_time_s"].max()
    else:
        a0 = a1 = np.nan
    su = m[m["decision"] == "SCALE_UP"]
    n_rps, n_req, n_err = summary(meta["normal_summary"])
    a_rps, a_req, a_err = summary(meta["attack_summary"])
    rt = pd.read_csv(meta["rtt_path"])
    rec = dict(meta)
    rec.update(dict(
        atk_ini=a0, atk_fim=a1,
        escalou=bool(len(su)), n_scale_up=len(su), max_inst=int(m["num_instances"].max()),
        escalou_no_ataque=bool(len(su[(su.elapsed_time_s > (a0 if a0 == a0 else 1e9)) &
                                       (su.elapsed_time_s <= (a1 if a1 == a1 else -1) + config.MONITOR_INTERVAL_SECONDS)])),
        cpu_media=m["average_cpu_percent"].iloc[1:].mean(), cpu_pico=m["average_cpu_percent"].iloc[1:].max(),
        normal_rps_real=n_rps, normal_req=n_req, normal_err=n_err,
        atk_rps_real=a_rps, atk_req=a_req, atk_err=a_err,
        n_rtt=len(rt), rtt_dur=rt["timestamp"].max() - rt["timestamp"].min(),
        base_mean=win["base_mean"].iloc[0], base_std=win["base_std"].iloc[0],
        n_base=win["n_base"].iloc[0], base_ok=bool(win["base_ok"].iloc[0]),
    ))
    win = win.drop(columns=["base_mean", "base_std", "n_base", "base_ok"])
    win.insert(0, "run_id", meta["familia"] + "/" + meta["suffix"])
    return rec, win


def _proc(args):
    return process(*args)


def validar(n_por_familia=6, seed=20260930):
    """Compara a decisão da reimplementação com o EntCusumZV3 original, em cópia temporária."""
    from EntCusumZV3 import PARAMS_ORIGINAIS, analisar_bursts_tunavel  # valida a reimplementação do ORIGINAL (§143)
    import matplotlib
    matplotlib.use("Agg")
    rng = np.random.default_rng(seed)
    runs = catalog()
    df = pd.DataFrame(runs)
    amostra = []
    for fam, g in df.groupby("familia"):
        idx = rng.choice(len(g), size=min(n_por_familia, len(g)), replace=False)
        amostra += [g.iloc[i].to_dict() for i in idx]
    tmp = tempfile.mkdtemp(prefix="valid_det_")  # cópia temporária -- original grava xlsx/png ao lado
    res = []
    for r in amostra:
        dst = os.path.join(tmp, "rtt_log_" + r["suffix"] + ".csv")
        shutil.copy(r["rtt_path"], dst)
        orig = analisar_bursts_tunavel(input_file=dst, show_plot=False, **PARAMS_ORIGINAIS)
        mine = detector_janelas(r["rtt_path"])
        st_mine = status_original(mine)
        st_orig = (orig["Status Burst"] == "DDoS Burst").values
        igual = len(st_mine) == len(st_orig) and bool((st_mine == st_orig).all())
        med_ok = len(st_mine) == len(st_orig) and np.allclose(
            orig["Média RTT"].astype(float).values, mine[mine.avaliada]["mean"].round(1).values, atol=0.051)
        res.append(dict(run=r["familia"] + "/" + r["suffix"], janelas_orig=len(st_orig), janelas_mine=len(st_mine),
                        alarmes_orig=int(st_orig.sum()), alarmes_mine=int(st_mine.sum()),
                        decisao_identica=igual, medias_identicas=med_ok))
    shutil.rmtree(tmp, ignore_errors=True)
    out = pd.DataFrame(res)
    os.makedirs(OUT_DIR, exist_ok=True)
    out.to_csv(os.path.join(OUT_DIR, "validacao.csv"), index=False)
    print(out.to_string(index=False))
    print(f"\nDecisão idêntica: {out.decisao_identica.sum()}/{len(out)} | médias idênticas: "
          f"{out.medias_identicas.sum()}/{len(out)} | alarmes totais orig={out.alarmes_orig.sum()} "
          f"mine={out.alarmes_mine.sum()}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validar", action="store_true")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--base", default=ER, help="diretório-raiz das famílias (ex.: backup pré-correção)")
    ap.add_argument("--familias", default=",".join(FAMILIAS))
    ap.add_argument("--tag", default="", help="sufixo dos arquivos de saída")
    a = ap.parse_args()
    if a.validar:
        validar()
        return
    runs = catalog(a.base, a.familias.split(","))
    print(f"{len(runs)} execuções no catálogo")
    with Pool(10) as p:
        res = p.map(_proc, [(r, a.window) for r in runs], chunksize=4)
    recs = [r for r, _ in res]
    wins = [w for _, w in res if w is not None]
    os.makedirs(OUT_DIR, exist_ok=True)
    sfx = ("" if a.window == 20 else f"_w{a.window}") + (f"_{a.tag}" if a.tag else "")
    pd.DataFrame(recs).to_csv(os.path.join(OUT_DIR, f"runs{sfx}.csv"), index=False)
    pd.concat(wins).to_csv(os.path.join(OUT_DIR, f"windows{sfx}.csv.gz"), index=False, compression="gzip")
    erros = [r for r in recs if r.get("erro")]
    print(f"Salvo runs{sfx}.csv ({len(recs)}) e windows{sfx}.csv.gz; erros: {len(erros)}")
    for e in erros[:10]:
        print("  ERRO", e["familia"], e["suffix"], e["erro"])


if __name__ == "__main__":
    main()
