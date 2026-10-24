import numpy as np, pandas as pd
from EntCusumZV3 import (bordas_log_baseline, histograma_faixas, divergencia_js,
                         z_robusto_params, Z_K_RECOMENDADO, Z_FRAC_RECOMENDADA,
                         ENTROPIA_BINS_RECOMENDADO, ENTROPIA_JS_RECOMENDADO)
H, RAZAO = 1000.0, 1.8
def corrige_t(r):
    r=r.sort_values("timestamp"); tt=(r.timestamp-r.timestamp.min()).values
    lac=np.diff(tt,prepend=tt[0]); return tt-np.cumsum(np.where(lac>2,lac,0)), r.rtt.values
def detecta(rtt, tag, bl_a, bl_b, a0, a1):
    tt,v=corrige_t(pd.read_csv(rtt))
    b=v[(tt>=bl_a)&(tt<bl_b)]; mu,sd=b.mean(),b.std()
    z_med,z_esc=z_robusto_params(b)
    bordas=bordas_log_baseline(b,ENTROPIA_BINS_RECOMENDADO); p_base=histograma_faixas(b,bordas)
    cc=0.0; cus=np.empty(len(v))
    for i,x in enumerate(v):
        cc=max(0.0,cc+(x-mu)-0.5*sd); cc=0.0 if cc>H*sd else cc; cus[i]=cc
    cA=zA=eA=comb=nj=0
    for t0 in np.arange(a0,a1-19.999,10):
        m=(tt>=t0)&(tt<t0+20)
        if m.sum()<10: continue
        nj+=1; w=v[m]
        zf=float(((w-z_med)/z_esc>Z_K_RECOMENDADO).mean()); z_d=zf>Z_FRAC_RECOMENDADA
        e_d=divergencia_js(histograma_faixas(w,bordas),p_base)>ENTROPIA_JS_RECOMENDADO
        c_d=cus[np.where(m)[0][-1]]>H*sd
        ma=w.mean()>RAZAO*mu
        cA+=c_d; zA+=z_d; eA+=e_d; comb+=(ma and (z_d or c_d))
    print(f"{tag:40s} baseline[{bl_a}-{bl_b}] mu={mu:5.2f} sd={sd:6.2f} floor={RAZAO*mu:5.2f} | "
          f"CUSUM {cA}/{nj}  Z {zA}/{nj}  ent {eA}/{nj}  comb {comb}/{nj}")

s="agg320_nwu10000_atk5pct_awu200000_rep1"
old=f"experiment_results/confirmacao_320/rtt_log_{s}.csv"
new=f"experiment_results/edos_furtivo_wu/rtt_log_{s}.csv"
print("--- ANTIGO (execução quente, 4 instâncias) ---")
detecta(old,"ANTIGO baseline CONTAMINADO (0-20)",0,20,20,160)
detecta(old,"ANTIGO baseline LIMPO (10-20)",10,20,20,160)
print("--- NOVO (execução fria, 3 instâncias) ---")
detecta(new,"NOVO baseline (t<60)",0,60,60,180)
detecta(new,"NOVO baseline LIMPO (10-60)",10,60,60,180)
