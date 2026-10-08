"""
Resumo do teste rápido run_normal_wu_teste.py (changes.txt §118). Só tabela,
sem gráfico. Referência WU=10: primeiros 60 s de normal_isolado_pos_lb/.
"""
import os

import numpy as np
import pandas as pd

AGGS = [20, 40, 80, 160, 320, 640]
FONTES = [(10, "experiment_results/normal_isolado_pos_lb", "agg{agg}_WU10_rep1")] + [
    (wu, "experiment_results/normal_wu_teste", f"agg{{agg}}_WU{wu}_rep1") for wu in (100, 1000, 10000)]
DUR = 60


def resumo(d, s):
    mf, rf, nf = (os.path.join(d, f"{p}_{s}.csv") for p in ("metrics", "rtt_log", "normal_traffic_summary_log"))
    if not os.path.exists(mf):
        return None
    m = pd.read_csv(mf)
    m = m[(m.elapsed_time_s > 0.5) & (m.elapsed_time_s <= DUR + 0.5)]
    r = pd.read_csv(rf).sort_values("timestamp")
    r["t"] = r.timestamp - r.timestamp.min()
    r = r[r.t < DUR]
    real = err = np.nan
    if os.path.exists(nf):
        n = pd.read_csv(nf)
        n = n[n.total_requests.notna()]
        if len(n):
            err = n.errors.sum()
            real = len(r) / DUR  # taxa entregue nos mesmos 60 s (o summary cobre a execução toda)
    base = r[r.t < 20].rtt
    jan = [r[(r.t >= a) & (r.t < a + 20)].rtt.mean() / base.mean() for a in (20, 30, 40)]
    return dict(cpu_media=m.average_cpu_percent.mean(), cpu_pico=m.average_cpu_percent.max(),
                inst_max=int(m.num_instances.max()), escalou=bool((m.decision == "SCALE_UP").any()),
                rps_real=real, erros=err, rtt_media=r.rtt.mean(), rtt_mediana=r.rtt.median(),
                rtt_dp=r.rtt.std(), rtt_p95=r.rtt.quantile(.95), rtt_p99=r.rtt.quantile(.99),
                cv=r.rtt.std() / r.rtt.mean(), razao_janela_max=max(jan))


rows = []
for wu, d, pat in FONTES:
    for agg in AGGS:
        x = resumo(d, pat.format(agg=agg))
        if x:
            rows.append(dict(wu=wu, agg=agg, **x))
df = pd.DataFrame(rows)
os.makedirs("experiment_results/normal_wu_teste", exist_ok=True)
df.to_csv("experiment_results/normal_wu_teste/resumo_normal_wu_teste.csv", index=False)
pd.set_option("display.width", 220)
for col in ["cpu_media", "cpu_pico", "inst_max", "rps_real", "erros", "rtt_mediana", "rtt_media",
            "rtt_dp", "rtt_p99", "razao_janela_max"]:
    print(f"\n--- {col} (linhas = WU, colunas = rps agregado nominal) ---")
    print(df.pivot(index="wu", columns="agg", values=col).round(2).to_string())
