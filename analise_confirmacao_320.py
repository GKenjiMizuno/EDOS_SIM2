"""
Análise de run_confirmacao_320.py (changes.txt §121). Só tabelas.
Por execução: instante do 1º SCALE_UP, se a instância extra foi mantida
durante o ataque, scale-downs, alarmes da regra combinada do EntCusumZV3
(reimplementação validada) nas 13 janelas de 20 s dentro do ataque
(t0 = 20..140 s) separados em ANTES e DEPOIS do escalonamento, e RTT/CPU no
regime pós-escalonamento. No controle (0%): escalonamento espontâneo e
alarme falso nas mesmas 13 janelas.
"""
import os

import numpy as np
import pandas as pd

from deteccao_pos_lb_extract import detector_janelas

import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="experiment_results/confirmacao_320")
ap.add_argument("--nwu", type=int, default=10000)
ap.add_argument("--cargas", default="320")
ap.add_argument("--intensidades", default="0,1,5")
ARGS = ap.parse_args()
D = ARGS.dir
POS = list(range(20, 141, 10))


def summ(f):
    try:
        x = pd.read_csv(f)
        x = x[x.total_requests.notna()]
        return x.real_rps.sum(), x.errors.sum()
    except FileNotFoundError:
        return np.nan, np.nan


rows = []
for agg, pct, rep in [(g, p, r) for g in map(int, ARGS.cargas.split(","))
                      for p in map(int, ARGS.intensidades.split(",")) for r in (1, 2, 3)]:
    if True:
        s = f"agg{agg}_nwu{ARGS.nwu}_atk{pct}pct_awu200000_rep{rep}"
        try:
            m = pd.read_csv(f"{D}/metrics_{s}.csv")
        except FileNotFoundError:
            print("[faltando]", s)
            continue
        su = m[m.decision == "SCALE_UP"].elapsed_time_s
        sd = m[m.decision == "SCALE_DOWN"].elapsed_time_s
        t_su = su.min() if len(su) else np.nan
        janela_atk = m[(m.elapsed_time_s > 20) & (m.elapsed_time_s <= 160.5)]
        pos_su = janela_atk[janela_atk.elapsed_time_s > (t_su if t_su == t_su else 1e9)]
        w = detector_janelas(f"{D}/rtt_log_{s}.csv")
        w = w[w.avaliada & w.t0.isin(POS)].copy()
        w["alarme"] = (w["mean"] > 1.8 * w.base_mean) & ((w.max_z > 3.5) | (w.cusum > 5 * w.base_std))
        w["razao"] = w["mean"] / w.base_mean
        antes = w[w.t0 < (t_su if t_su == t_su else 1e9)]
        depois = w[w.t0 >= (t_su if t_su == t_su else 1e9)]
        r = pd.read_csv(f"{D}/rtt_log_{s}.csv").sort_values("timestamp")
        r["t"] = r.timestamp - r.timestamp.min()
        b = r[r.t < 20].rtt
        pr = r[(r.t >= (t_su + 10 if t_su == t_su else 30)) & (r.t < 160)].rtt
        nr, ne = summ(f"{D}/normal_traffic_summary_log_{s}.csv")
        ar, ae = summ(f"{D}/attack_summary_log_{s}.csv")
        rows.append(dict(
            carga=agg, intensidade=pct, rep=rep,
            primeiro_scale_up=t_su, n_scale_up=len(su), n_scale_down=len(sd),
            scale_down_durante_ataque=int(((sd > 20) & (sd <= 160)).sum()),
            inst_max=int(m.num_instances.max()),
            pct_ataque_com_2mais_inst=round(100 * (janela_atk.num_instances >= 2).mean(), 0),
            cpu_antes=round(m[(m.elapsed_time_s > 0.5) & (m.elapsed_time_s <= 20)].average_cpu_percent.mean(), 1),
            cpu_pos_escalonamento=round(pos_su.average_cpu_percent.mean(), 1) if len(pos_su) else np.nan,
            alarmes_total=f"{int(w.alarme.sum())}/{len(w)}",
            alarmes_antes_escal=f"{int(antes.alarme.sum())}/{len(antes)}",
            alarmes_depois_escal=f"{int(depois.alarme.sum())}/{len(depois)}",
            razao_max_depois=round(depois.razao.max(), 2) if len(depois) else np.nan,
            rtt_media_pos_vs_base=round(pr.mean() / b.mean(), 2),
            rtt_mediana_pos_vs_base=round(pr.median() / b.median(), 2),
            rtt_base_ms=round(b.mean(), 2),
            normal_real=round(nr, 1), atk_real=round(ar, 2) if ar == ar else "-",
            erros_normal=ne, erros_atk=ae if ae == ae else "-"))
df = pd.DataFrame(rows)
df.to_csv(f"{D}/resumo_{os.path.basename(D)}.csv", index=False)
pd.set_option("display.width", 260)
print(df.to_string(index=False))
