import pandas as pd, glob, os
D="experiment_results/desempate_combinado_isolado"; NB="experiment_results/normal_baseline"
def head(path,tag,n=12):
    if not os.path.exists(path): print(f"[faltando] {path}"); return
    m=pd.read_csv(path)
    print(f"\n== {tag} ==")
    print("  t:", " ".join(f"{r.elapsed_time_s:.0f}s={r.average_cpu_percent:.0f}%/{int(r.num_instances)}i" for _,r in m.head(n).iterrows()))
    chg=m[m.num_instances.diff().fillna(0)!=0]
    print("  escalonamentos:", list(zip(chg.elapsed_time_s.round().astype(int), chg.num_instances.astype(int))))
    print(f"  CPU pico={m.average_cpu_percent.max():.0f}%  inst_max={int(m.num_instances.max())}")
# normal isolado agg40 (referência do 27)
head(f"{NB}/metrics_normal_agg40_WU10_refined_rep1.csv","NORMAL agg40 WU10 rep1")
# painéis de ataque mais pesados do 27
for cond in ("combinado","isolado"):
    for rps,wu in [(10,400000),(10,200000),(1,100000)]:
        head(f"{D}/metrics_{cond}_rps{rps}_att4_WU{wu}_rep1.csv", f"{cond} rps{rps} WU{wu} rep1")
