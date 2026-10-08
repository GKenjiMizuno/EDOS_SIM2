"""
Resumo de run_ataque_wu_teste.py (changes.txt §119-§120): dano, CPU, RTT
(média e mediana vs baseline t<20 s) e alarmes da regra combinada do
EntCusumZV3 (reimplementação validada em deteccao_pos_lb_extract.py) nas
janelas de 20 s inteiramente dentro do ataque [20,60] s (t0 = 20, 30, 40).
Controle sem ataque: normal_wu_teste agg{160,320}_WU10000. Só tabela.
"""
import numpy as np
import pandas as pd

from deteccao_pos_lb_extract import detector_janelas

D_ATK = "experiment_results/ataque_wu_teste"
D_NOR = "experiment_results/normal_wu_teste"


def summ(f):
    try:
        x = pd.read_csv(f)
        x = x[x.total_requests.notna()]
        return x.real_rps.sum(), x.errors.sum()
    except FileNotFoundError:
        return np.nan, np.nan


def linha(carga, pct, d, s):
    m = pd.read_csv(f"{d}/metrics_{s}.csv")
    r = pd.read_csv(f"{d}/rtt_log_{s}.csv").sort_values("timestamp")
    r["t"] = r.timestamp - r.timestamp.min()
    r = r[r.t < 60]
    b, a = r[r.t < 20].rtt, r[(r.t >= 20) & (r.t < 60)].rtt
    w = detector_janelas(f"{d}/rtt_log_{s}.csv")
    pos = w[w.avaliada & w.t0.isin([20, 30, 40])]
    al = (pos["mean"] > 1.8 * pos.base_mean) & ((pos.max_z > 3.5) | (pos.cusum > 5 * pos.base_std))
    su = m[m.decision == "SCALE_UP"]
    nr, ne = summ(f"{d}/normal_traffic_summary_log_{s}.csv")
    ar, ae = summ(f"{d}/attack_summary_log_{s}.csv")
    cpu_atk = m[(m.elapsed_time_s > 20) & (m.elapsed_time_s <= 60.5)].average_cpu_percent
    return dict(
        carga_normal=carga, intensidade=pct,
        escalou=(f"sim t={su.elapsed_time_s.min():.0f}s" if len(su) else "não"),
        inst_max=int(m.num_instances.max()),
        cpu_antes=round(m[(m.elapsed_time_s > 0.5) & (m.elapsed_time_s <= 20)].average_cpu_percent.mean(), 1),
        cpu_atk_media=round(cpu_atk.mean(), 1), cpu_atk_pico=round(cpu_atk.max(), 1),
        rtt_base=round(b.mean(), 2), razao_media=round(a.mean() / b.mean(), 2),
        razao_mediana=round(a.median() / b.median(), 2),
        razao_max_janela=round((pos["mean"] / pos.base_mean).max(), 2),
        alarmes=f"{int(al.sum())}/{len(pos)}",
        normal_real=round(nr, 1), atk_real=round(ar, 2) if ar == ar else "-",
        erros_normal=ne, erros_atk=ae if ae == ae else "-")


rows = []
for carga in (160, 320):
    rows.append(linha(carga, 0, D_NOR, f"agg{carga}_WU10000_rep1"))
    for pct in (1, 5, 10, 15, 20, 25):
        s = f"agg{carga}_nwu10000_atk{pct}pct_awu200000_rep1"
        try:
            rows.append(linha(carga, pct, D_ATK, s))
        except FileNotFoundError:
            print("[faltando]", s)
df = pd.DataFrame(rows)
df.to_csv(f"{D_ATK}/resumo_ataque_wu_teste.csv", index=False)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
