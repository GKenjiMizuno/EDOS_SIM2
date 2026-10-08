"""
Detecção em TODO o atacantes_intensidade_grid (S1-S11 x intensidade x nº de
atacantes, WU de ataque 200.000) e tabela de células "furtivas que escalaram"
(changes.txt §132). Só tabelas, sem Docker.

Por execução, no tempo do rtt_log corrigido dos saltos de relógio do WSL2
(§128): baseline = RTT em t < 20 s; janelas de 20 s, passo 10 s; avaliadas as
13 janelas t0 = 20..140 (inteiras dentro do ataque 20-160 s).
Detectores (alarme da execução = >= 1 das 13 janelas):
  R1   = EntCusumZV3 padrão: média > 1,8x baseline E (Z > 3,5 OU CUSUM > 5σ)
  C1k  = CUSUM sozinho, h = 1000σ (§125/§129; dentro do ataque o reset do §131
         não muda a detecção, só o comportamento depois)
  MED  = só a regra da média (> 1,8x)
Escalou = SCALE_UP em (20, 160] s. Pico de arranque (SCALE_UP <= 20 s) é
  marcado à parte. FURTIVA E ESCALOU = escalou no ataque e o detector não
  alarmou em nenhuma das 13 janelas.
S9-S11: gerador do cliente no teto de GIL (§113) -- marcados.

Saídas: experiment_results/deteccao_pos_lb/resultados/
  T19_atacantes_intensidade_execucoes.csv e T19_atacantes_intensidade_celulas.csv
"""
import glob
import os
import re
from multiprocessing import Pool

import numpy as np
import pandas as pd

D = "experiment_results/atacantes_intensidade_grid"
OUT = "experiment_results/deteccao_pos_lb/resultados"
RX = re.compile(r"metrics_(S\d+)_atk([\d.]+)pct_att(\d)_wu(\d+)_rep(\d+)\.csv")
NORMAL = {"S1": 40, "S2": 100, "S3": 200, "S4": 300, "S5": 20, "S6": 80, "S7": 160,
          "S8": 320, "S9": 640, "S10": 1280, "S11": 2560}
GIL = {"S9", "S10", "S11"}
POS_T0 = np.arange(20, 141, 10)


def processa(mp):
    cen, pct, att, wu, rep = RX.search(os.path.basename(mp)).groups()
    suf = os.path.basename(mp)[len("metrics_"):-4]
    m = pd.read_csv(mp)
    su = m[m.decision == "SCALE_UP"].elapsed_time_s
    r = pd.read_csv(f"{D}/rtt_log_{suf}.csv").sort_values("timestamp")
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
    k_r1 = k_c = k_m = 0
    prev, razoes = None, []
    for t0 in np.arange(0, 141, 10):
        msk = (tt >= t0) & (tt < t0 + 20)
        if msk.sum() < 10:
            prev = None
            continue
        w = v[msk]
        zmax = float(np.max(np.abs((w - prev[0]) / prev[1]))) if prev and prev[1] > 0 else 0.0
        prev = (w.mean(), w.std(ddof=1))
        if t0 < 20:
            continue
        cs = cus[np.where(msk)[0][-1]]
        razao = w.mean() / mu
        razoes.append(razao)
        k_r1 += (razao > 1.8) and (zmax > 3.5 or cs > 5)
        k_c += cs > 1000
        k_m += razao > 1.8
    try:
        x = pd.read_csv(f"{D}/normal_traffic_summary_log_{suf}.csv")
        x = x[x.total_requests.notna()]
        nreq, nerr, nrps = x.total_requests.sum(), x.errors.sum(), x.real_rps.sum()
    except FileNotFoundError:
        nreq = nerr = nrps = np.nan
    return dict(cenario=cen, normal_rps=NORMAL[cen], pct=float(pct), atacantes=int(att), rep=int(rep), execucao=suf,
                escalou=bool(((su > 20) & (su <= 160)).any()), arranque=bool((su <= 20).any()),
                n_scale_up=int(((su > 20) & (su <= 160)).sum()), inst_max=int(m.num_instances.max()),
                cpu_pico=m.average_cpu_percent.max(),
                r1=k_r1 > 0, c1k=k_c > 0, med=k_m > 0, k_r1=k_r1, k_c1k=k_c, k_med=k_m,
                razao_mediana=float(np.median(razoes)) if razoes else np.nan,
                cusum_max=float(cus[(tt >= 20) & (tt <= 160)].max()),
                rtt_base_ms=mu, erro_normal_pct=100 * nerr / nreq if nreq else np.nan,
                normal_entregue_pct=100 * nrps / NORMAL[cen])


if __name__ == "__main__":
    arqs = sorted(glob.glob(f"{D}/metrics_*.csv"))
    with Pool(6) as p:
        E = pd.DataFrame(p.map(processa, arqs))
    E["gil"] = E.cenario.isin(GIL)
    for d in ("r1", "c1k", "med"):
        E[f"furtiva_escalou_{d}"] = E.escalou & ~E[d]
    os.makedirs(OUT, exist_ok=True)
    E.to_csv(f"{OUT}/T19_atacantes_intensidade_execucoes.csv", index=False)

    ordem = sorted(NORMAL, key=lambda s: int(s[1:]))
    C = E.groupby(["cenario", "normal_rps", "pct", "atacantes"]).agg(
        n=("rep", "size"), escalou=("escalou", "sum"), arranque=("arranque", "sum"),
        inst_max=("inst_max", "max"), det_r1=("r1", "sum"), det_c1k=("c1k", "sum"), det_med=("med", "sum"),
        furt_esc_r1=("furtiva_escalou_r1", "sum"), furt_esc_c1k=("furtiva_escalou_c1k", "sum"),
        furt_esc_med=("furtiva_escalou_med", "sum"),
        razao_med=("razao_mediana", "median"), erro_normal=("erro_normal_pct", "mean"),
        entregue=("normal_entregue_pct", "mean"), gil=("gil", "first")).reset_index()
    C["ord"] = C.cenario.map({s: i for i, s in enumerate(ordem)})
    C = C.sort_values(["ord", "pct", "atacantes"]).drop(columns="ord")
    C.to_csv(f"{OUT}/T19_atacantes_intensidade_celulas.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    print("execuções:", len(E), "| escalaram no ataque:", int(E.escalou.sum()),
          "| pico de arranque (<=20 s):", int(E.arranque.sum()))
    for d, nome in (("r1", "R1 (EntCusumZV3 padrão)"), ("c1k", "CUSUM 1000σ"), ("med", "média 1,8x")):
        f = E[f"furtiva_escalou_{d}"]
        print(f"FURTIVA E ESCALOU por {nome}: {int(f.sum())} execuções "
              f"({int(f[~E.gil].sum())} fora de S9-S11)")
    print(C.round(2).to_string(index=False))
    print("\nexecuções furtivas que escalaram (qualquer detector):")
    q = E[E.furtiva_escalou_r1 | E.furtiva_escalou_c1k | E.furtiva_escalou_med]
    print(q[["execucao", "inst_max", "n_scale_up", "r1", "c1k", "med", "k_med", "razao_mediana", "cusum_max",
             "rtt_base_ms", "normal_entregue_pct", "gil"]].round(2).to_string(index=False))
