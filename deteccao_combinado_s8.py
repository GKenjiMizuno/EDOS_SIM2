"""
Detecção (changes.txt §127) no combinado rps10/att4/WU=400.000 (fonte do
gráfico 27, desempate_combinado_isolado) e em todo o S8 do
atacantes_intensidade_grid (320 rps normal, 1-25%, 1/2/4 atacantes,
WU=200.000), com controles normal_baseline agg40/agg320 (10 reps).
Mesmo protocolo do §117: 13 janelas de 20 s, t0 = 20..140 s.
Detectores: R1 original (média > 1,8x baseline E (Z > 3,5 OU CUSUM > 5σ))
e CUSUM sozinho com h = 1000σ (§125). Também: escalonamento, CPU, erros.
Só tabelas. Saída: experiment_results/deteccao_pos_lb/resultados/T17_*.csv
"""
import glob
import os
import re

import numpy as np
import pandas as pd

from deteccao_pos_lb_extract import detector_janelas

POS = list(range(20, 141, 10))
H = 1000
OUT = "experiment_results/deteccao_pos_lb/resultados"
GRUPOS = [
    ("combinado_rps10_WU400k", "experiment_results/desempate_combinado_isolado",
     r"combinado_rps10_att4_WU400000_rep\d+"),
    ("controle_agg40", "experiment_results/normal_baseline", r"normal_agg40_WU10_refined_rep\d+"),
    ("S8", "experiment_results/atacantes_intensidade_grid", r"S8_atk\d+pct_att\d_wu200000_rep\d+"),
    ("controle_agg320", "experiment_results/normal_baseline", r"normal_agg320_WU10_refined_rep\d+"),
]


def summ(path):
    try:
        x = pd.read_csv(path)
        x = x[x.total_requests.notna()]
        return int(x.total_requests.sum()), int(x.errors.sum())
    except FileNotFoundError:
        return np.nan, np.nan


rows = []
for grupo, d, rx in GRUPOS:
    for mp in sorted(glob.glob(f"{d}/metrics_*.csv")):
        suf = os.path.basename(mp)[len("metrics_"):-4]
        if not re.fullmatch(rx, suf):
            continue
        rtt = f"{d}/rtt_log_{suf}.csv"
        m = pd.read_csv(mp)
        w = detector_janelas(rtt)
        w = w[w.avaliada & w.t0.isin(POS)]
        r1 = (w["mean"] > 1.8 * w.base_mean) & ((w.max_z > 3.5) | (w.cusum > 5 * w.base_std))
        c1k = w.cusum_sd > H
        su = m[m.decision == "SCALE_UP"].elapsed_time_s
        dt = m.elapsed_time_s.diff().median()
        mm = re.search(r"atk(\d+)pct_att(\d)", suf)
        nreq, nerr = summ(f"{d}/normal_traffic_summary_log_{suf}.csv")
        areq, aerr = summ(f"{d}/attack_summary_log_{suf}.csv")
        rows.append(dict(
            grupo=grupo, execucao=suf,
            intensidade=int(mm.group(1)) if mm else (100 if grupo.startswith("comb") else 0),
            atacantes=int(mm.group(2)) if mm else (4 if grupo.startswith("comb") else 0),
            janelas=len(w),
            r1_alarmes=int(r1.sum()), r1_detectou=bool(r1.any()),
            c1000_alarmes=int(c1k.sum()), c1000_detectou=bool(c1k.any()),
            c1000_primeiro=float(w[c1k].t0.min() + 20) if c1k.any() else np.nan,
            media_maior_1_8=int((w["mean"] > 1.8 * w.base_mean).sum()),
            cusum_max_sigma=round(float(w.cusum_sd.max()), 1),
            inst_max=int(m.num_instances.max()), n_scale_up=len(su),
            primeiro_scale_up=float(su.min()) if len(su) else np.nan,
            inst_extra_s=float(((m.num_instances - 1).clip(lower=0) * dt).sum()),
            cpu_media_ataque=round(m[(m.elapsed_time_s > 20) & (m.elapsed_time_s <= 160)].average_cpu_percent.mean(), 1),
            cpu_pico=round(m.average_cpu_percent.max(), 1),
            normal_req=nreq, normal_err=nerr, atk_req=areq, atk_err=aerr))

df = pd.DataFrame(rows)
os.makedirs(OUT, exist_ok=True)
df.to_csv(f"{OUT}/T17_combinado_s8_execucoes.csv", index=False)

pd.set_option("display.width", 250)
agg = df.groupby(["grupo", "intensidade", "atacantes"], sort=False).agg(
    n=("execucao", "size"),
    r1_det=("r1_detectou", "sum"), c1000_det=("c1000_detectou", "sum"),
    c1000_alarmes_med=("c1000_alarmes", "mean"), c1000_1o_med=("c1000_primeiro", "median"),
    cusum_max_med=("cusum_max_sigma", "median"),
    escalaram=("n_scale_up", lambda s: int((s > 0).sum())), scale_ups=("n_scale_up", "sum"),
    inst_max=("inst_max", "max"), inst_max_lista=("inst_max", lambda s: ",".join(map(str, s))),
    inst_extra_s_med=("inst_extra_s", "mean"), su_1o_med=("primeiro_scale_up", "median"),
    cpu_pico_med=("cpu_pico", "median"), cpu_atk_med=("cpu_media_ataque", "median"),
    err_normal_pct=("normal_err", "sum"), req_normal=("normal_req", "sum"),
    err_atk=("atk_err", "sum"), req_atk=("atk_req", "sum")).reset_index()
agg["err_normal_pct"] = (100 * agg.err_normal_pct / agg.req_normal).round(2)
agg["err_atk_pct"] = (100 * agg.err_atk / agg.req_atk).round(2)
agg = agg.drop(columns=["req_normal", "err_atk", "req_atk"]).round(1)
agg.to_csv(f"{OUT}/T17_combinado_s8_resumo.csv", index=False)
print(agg.to_string(index=False))
