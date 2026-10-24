import os, re, glob, shutil, pandas as pd
DST="experiment_results/edos_furtivo_robusto"; os.makedirs(DST, exist_ok=True)
RPS=[160,320]; WUN=[10,100,1000,10000]; WUA=[10000,20000,50000,100000,200000]; INT=[1,5,10,15,20,25]
grid=set((r,wn,wa,p) for r in RPS for wn in WUN for wa in WUA if wa>wn for p in INT)
PREF=["metrics","rtt_log","attack_summary_log","normal_traffic_summary_log","traffic_capture"]
SRCS=["edos_furtivo_wu","edos_furtivo_wu_rps"]

def dur_ok(path):
    try: return pd.read_csv(path).elapsed_time_s.max()>=230
    except: return False

def copia_por_sufixo(src_suf, dst_suf):
    n=0
    for d in SRCS:
        for pre in PREF:
            s=f"experiment_results/{d}/{pre}_{src_suf}.csv"
            t=f"{DST}/{pre}_{dst_suf}.csv"
            if os.path.exists(s) and not os.path.exists(t):
                shutil.copy2(s,t); n+=1
    return n

# 1) células de ataque reaproveitáveis (sufixo idêntico)
atk=0
for (r,wn,wa,p) in grid:
    suf=f"agg{r}_nwu{wn}_atk{p}pct_awu{wa}_rep1"
    # confirma que existe em 240s
    src_metrics=[f"experiment_results/{d}/metrics_{suf}.csv" for d in SRCS]
    if any(os.path.exists(m) and dur_ok(m) for m in src_metrics):
        if not os.path.exists(f"{DST}/metrics_{suf}.csv"):
            copia_por_sufixo(suf, suf); atk+=1

# 2) baselines 0% existentes -> renomeia p/ convenção sem awu
base_copiadas=[]
for r in RPS:
    for wn in WUN:
        dst_suf=f"agg{r}_nwu{wn}_atk0pct_rep1"
        if os.path.exists(f"{DST}/metrics_{dst_suf}.csv"): continue
        # procura em ambas as pastas, com ou sem _awu200000
        for d in SRCS:
            for cand in [f"agg{r}_nwu{wn}_atk0pct_rep1", f"agg{r}_nwu{wn}_atk0pct_awu200000_rep1"]:
                m=f"experiment_results/{d}/metrics_{cand}.csv"
                if os.path.exists(m) and dur_ok(m):
                    copia_por_sufixo(cand, dst_suf); base_copiadas.append((r,wn)); break
            else: continue
            break

print(f"Células de ataque reaproveitadas copiadas: {atk}")
print(f"Baselines copiados: {len(base_copiadas)} -> {sorted(base_copiadas)}")
print(f"metrics agora em {DST}: {len(glob.glob(DST+'/metrics_*.csv'))}")
