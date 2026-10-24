import numpy as np, pandas as pd

def corrige_t(r):
    r = r.sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    return tt, r.rtt.values

def janela(tt, v, a, b):
    m=(tt>=a)&(tt<b); w=v[m]
    return f"n={len(w):5d} media={w.mean():6.2f} mediana={np.median(w):6.2f} p95={np.percentile(w,95):6.1f}" if len(w) else "vazio"

def cpu_jan(m, a, b):
    w=m[(m.elapsed_time_s>=a)&(m.elapsed_time_s<b)]
    return f"CPU media={w.average_cpu_percent.mean():5.1f}% max={w.average_cpu_percent.max():6.1f}% inst~{w.num_instances.mode().iloc[0] if len(w) else '-'}"

def dump(rtt,met,tag,a0,a1):
    tt,v=corrige_t(pd.read_csv(rtt)); m=pd.read_csv(met)
    print(f"\n==== {tag}  (ataque {a0}-{a1}s) ====")
    print(f"  RTT arranque  t<10 :", janela(tt,v,0,10))
    print(f"  RTT 10-{a0:>3}s(norm):", janela(tt,v,10,a0))
    print(f"  RTT ataque {a0}-{a1} :", janela(tt,v,a0,a1))
    print(f"  RTT pos-ataque     :", janela(tt,v,a1,a1+40))
    print(f"  CPU arranque 0-10  :", cpu_jan(m,0,10))
    print(f"  CPU normal 10-{a0}  :", cpu_jan(m,10,a0))
    print(f"  CPU ataque {a0}-{a1} :", cpu_jan(m,a0,a1))
    # linha do tempo de instancias
    chg = m[m.num_instances.diff().fillna(0)!=0][["elapsed_time_s","num_instances"]]
    print(f"  mudancas de instancia:", list(zip(chg.elapsed_time_s.round().astype(int), chg.num_instances.astype(int))))

for rep in (1,):
    s=f"agg320_nwu10000_atk5pct_awu200000_rep{rep}"
    dump(f"experiment_results/confirmacao_320/rtt_log_{s}.csv",
         f"experiment_results/confirmacao_320/metrics_{s}.csv", f"ANTIGO(71) rep{rep}", 20,160)
s="agg320_nwu10000_atk5pct_awu200000_rep1"
dump(f"experiment_results/edos_furtivo_wu/rtt_log_{s}.csv",
     f"experiment_results/edos_furtivo_wu/metrics_{s}.csv", "NOVO rep1", 60,180)
