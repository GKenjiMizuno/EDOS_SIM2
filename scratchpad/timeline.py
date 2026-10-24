import pandas as pd
s="agg320_nwu10000_atk5pct_awu200000_rep1"
old=pd.read_csv(f"experiment_results/confirmacao_320/metrics_{s}.csv")
new=pd.read_csv(f"experiment_results/edos_furtivo_wu/metrics_{s}.csv")
def show(m,tag,atk):
    print(f"\n==== {tag} (ataque começa em {atk}s) ====")
    print(" t(s) inst  CPU%   label")
    for _,r in m.iterrows():
        if r.elapsed_time_s<=max(atk+30, 70):
            print(f"{r.elapsed_time_s:5.0f} {int(r.num_instances):4d} {r.average_cpu_percent:6.1f}   {r.label}")
show(old,"ANTIGO",20)
show(new,"NOVO",60)
