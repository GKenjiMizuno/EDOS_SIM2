import numpy as np, pandas as pd
import plot_edos_furtivo_wu_rps as base
base.D = "experiment_results/edos_furtivo_wu_baixo"

CELULAS = [(10000,15),(10000,20),(10000,30),(20000,15)]
REPS = [1,2,3,4,5]
RPS, WU_N = 320, 5000

def analisa(wu_a, pct, rep):
    suf = f"agg{RPS}_nwu{WU_N}_atk{pct}pct_awu{wu_a}_rep{rep}"
    carga = base.carrega(suf)
    if carga is None: return None
    m, r = carga
    mu, sd, jan, _ = base.detectores(r)                 # baseline aparado [15,60)
    dentro = jan[(jan.fim-20>=base.A0)&(jan.fim<=base.A1)]
    escalou = bool(((m.decision=="SCALE_UP")&(m.elapsed_time_s>base.A0)&(m.elapsed_time_s<=base.A1)).any())
    comb = int(dentro.comb.sum()); cus=int(dentro.cusum.sum()); z=int(dentro.z.sum()); e=int(dentro.ent.sum())
    nj = len(dentro)
    furtivo = escalou and comb==0
    return dict(wu_a=wu_a, pct=pct, rep=rep, escalou=escalou, inst_max=int(m.num_instances.max()),
                cpu_pico=round(m.average_cpu_percent.max(),1), comb=comb, cusum=cus, z=z, ent=e, nj=nj, furtivo=furtivo)

rows=[analisa(w,p,rp) for (w,p) in CELULAS for rp in REPS]
df=pd.DataFrame([x for x in rows if x])
print("\n=== POR REP ===")
for (w,p),g in df.groupby(["wu_a","pct"]):
    print(f"\nWU_ataque={w} intens={p}% (razão {w/WU_N:.0f}x):")
    for _,r in g.iterrows():
        print(f"  rep{r.rep}: escalou={r.escalou} inst={r.inst_max} cpu={r.cpu_pico} | "
              f"comb {r.comb}/{r.nj} cusum {r.cusum} z {r.z} ent {r.ent}" + ("  FURTIVO" if r.furtivo else ""))

print("\n=== RESUMO (5 reps) ===")
ag=df.groupby(["wu_a","pct"]).agg(
    escalou_em=("escalou","sum"), furtivo_em=("furtivo","sum"),
    comb_medio=("comb","mean"), inst_max=("inst_max","max"), n=("rep","count")).reset_index()
ag["razao"]=(ag.wu_a/WU_N).astype(int)
for _,r in ag.iterrows():
    print(f"WU_a={int(r.wu_a)} ({r.razao}x) {int(r.pct)}%: escalou {int(r.escalou_em)}/5 · "
          f"FURTIVO-e-escalou {int(r.furtivo_em)}/5 · combinado médio {r.comb_medio:.1f}/11 · inst_max {int(r.inst_max)}")
df.to_csv("experiment_results/edos_furtivo_wu_baixo/confirma_5reps.csv", index=False)
