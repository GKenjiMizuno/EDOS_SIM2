import numpy as np, pandas as pd
import plot_edos_furtivo_wu_rps as base
base.D="experiment_results/edos_furtivo_robusto"
suf="agg320_nwu100_atk25pct_awu20000_rep1"
m,r=base.carrega(suf)
v=r.rtt.values; tt=r.t.values
b=v[(tt>=15)&(tt<60)]; mu,sd=b.mean(),b.std()
atk=v[(tt>=60)&(tt<180)]
print(f"baseline [15,60): μ={mu:.3f}ms σ={sd:.3f}ms  (n={len(b)}, ~{len(b)/45:.0f}/s)")
print(f"ataque  [60,180): média={atk.mean():.3f}ms mediana={np.median(atk):.3f}ms p95={np.percentile(atk,95):.2f} (n={len(atk)}, ~{len(atk)/120:.0f}/s)")
print(f"razão da média do ataque sobre baseline: {atk.mean()/mu:.2f}x   (piso do combinado = 1,8x)")
print(f"elevação média por amostra no ataque: (x-μ)/σ = {(atk.mean()-mu)/sd:.3f}σ   (κ do CUSUM = 0,5σ)")
# CUSUM passo a passo
kappa=0.5*sd; H=1000*sd
c=0.0; fire_i=None; cmax=0
contrib_atk=[]
for i,x in enumerate(v):
    inc=(x-mu)-kappa
    c=max(0.0,c+inc)
    if 60<=tt[i]<180: contrib_atk.append(inc)
    if c>cmax: cmax=c
    if c>H and fire_i is None: fire_i=i
contrib_atk=np.array(contrib_atk)
print(f"\nCUSUM: κ={kappa:.3f}ms  h=1000σ={H:.0f}ms")
print(f"incremento médio por amostra NO ATAQUE: {contrib_atk.mean():.4f}ms  (positivo => acumula)")
print(f"  fração de amostras do ataque com incremento>0: {(contrib_atk>0).mean()*100:.1f}%")
print(f"CUSUM máximo atingido: {cmax:.0f}ms = {cmax/sd:.0f}σ   (dispara se > 1000σ)")
print(f"disparou? {'SIM em t=%.0fs'%tt[fire_i] if fire_i else 'NÃO'}")
# vereditos por janela
mu2,sd2,jan,_=base.detectores(r)
d=jan[(jan.fim-20>=60)&(jan.fim<=180)]
print(f"\nvereditos no ataque (11 janelas): CUSUM {int(d.cusum.sum())} · Z {int(d.z.sum())} · ent {int(d.ent.sum())} · combinado {int(d.comb.sum())}")
print(f"escalou no ataque? {bool(((m.decision=='SCALE_UP')&(m.elapsed_time_s>60)&(m.elapsed_time_s<=180)).any())}  CPU pico {m.average_cpu_percent.max():.0f}%")
