import numpy as np, pandas as pd
import plot_edos_furtivo_wu_rps as base
base.D = "experiment_results/edos_furtivo_robusto"
CELULAS=[(160,10000,20000,25),(320,1000,20000,20),(320,10000,50000,15)]
REPS=[1,2,3,4,5]

def analisa(rps,wn,wa,pct,rep):
    suf=f"agg{rps}_nwu{wn}_atk{pct}pct_awu{wa}_rep{rep}"
    carga=base.carrega(suf)
    if carga is None: return None
    m,r=carga
    mu,sd,jan,_=base.detectores(r)
    dentro=jan[(jan.fim-20>=base.A0)&(jan.fim<=base.A1)]
    esc=bool(((m.decision=="SCALE_UP")&(m.elapsed_time_s>base.A0)&(m.elapsed_time_s<=base.A1)).any())
    comb=int(dentro.comb.sum())
    return dict(cel=f"{rps}/WUn{wn}/WUa{wa}/{pct}%",rep=rep,escalou=esc,
                inst=int(m.num_instances.max()),cpu=round(m.average_cpu_percent.max(),1),
                comb=comb,cusum=int(dentro.cusum.sum()),z=int(dentro.z.sum()),ent=int(dentro.ent.sum()),
                furtivo=esc and comb==0)
rows=[analisa(*c,rp) for c in CELULAS for rp in REPS]
df=pd.DataFrame([x for x in rows if x])
print("=== POR REP ===")
for cel,g in df.groupby("cel",sort=False):
    print(f"\n{cel} (razão {int(g.iloc[0].name==g.iloc[0].name) and ''}):")
    for _,r in g.iterrows():
        print(f"  rep{r.rep}: escalou={r.escalou} inst={r.inst} cpu={r.cpu} | comb {r.comb}/11 cusum {r.cusum} z {r.z} ent {r.ent}"+("  FURTIVO" if r.furtivo else ""))
print("\n=== RESUMO (5 reps) ===")
for cel,g in df.groupby("cel",sort=False):
    print(f"{cel}: escalou {int(g.escalou.sum())}/5 · FURTIVO-e-escalou {int(g.furtivo.sum())}/5 · combinado médio {g.comb.mean():.1f}/11")
df.to_csv("experiment_results/edos_furtivo_robusto/confirma_robusto_5reps.csv",index=False)
