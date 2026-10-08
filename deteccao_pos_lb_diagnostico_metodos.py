"""Diagnóstico por janela de Z-score, CUSUM e entropia (changes.txt §124): fração de amostras
|z|>3.5, Z máx, CUSUM/σ no fim e no máximo da janela, picos > μ+5,5σ, ocupação do 1º bin
da entropia. Saída: experiment_results/deteccao_pos_lb/resultados/T16_diagnostico_metodos_janelas.csv.gz.
Uso: python3 deteccao_pos_lb_diagnostico_metodos.py"""
import pandas as pd, numpy as np
from multiprocessing import Pool
from scipy.stats import norm, kurtosis, skew

D="experiment_results/deteccao_pos_lb/"
t=pd.read_csv(D+"resultados/execucoes_avaliadas.csv")
ok=(t.atk_ini.sub(20).abs()<1)&(t.atk_fim.sub(160).abs()<2); gil=t.gil.fillna(False).astype(bool)
neg=t[(~t.ataque)&(t.normal_nom<=640)&(t.normal_wu==10)]; pos=t[t.ataque&~gil&ok]
def diag(args):
    rid,path,ataque=args
    d=pd.read_csv(path).sort_values("timestamp"); tt=(d.timestamp-d.timestamp.min()).values; v=d.rtt.values
    b=v[tt<20]; mu,sd=b.mean(),b.std(ddof=1)
    vmin,vmax=v.min(),v.max()
    out=[]; prev=None; cs=0.0; cusum=np.empty(len(v))
    for i,x in enumerate(v):
        cs=max(0.0,cs+(x-mu)-0.5*sd); cusum[i]=cs
    for t0 in range(20,141,10):
        m=(tt>=t0)&(tt<t0+20); w=v[m]
        if len(w)<10: continue
        # Z do detector (vs janela anterior)
        pm=(tt>=t0-10)&(tt<t0+10); pw=v[pm]
        zmax=np.max(np.abs((w-pw.mean())/pw.std(ddof=1)))
        frac_z=np.mean(np.abs((w-pw.mean())/pw.std(ddof=1))>3.5)
        # CUSUM: alarme na ultima amostra; quantas amostras individuais sozinhas > mu+5.5sd
        csw=cusum[np.where(m)[0]]
        hist,_=np.histogram(w,bins=10,range=(vmin,vmax))
        out.append(dict(run_id=rid,ataque=ataque,t0=t0,n=len(w),zmax=zmax,frac_amostras_z35=frac_z,
            cusum_fim_sd=csw[-1]/sd, cusum_max_sd=csw.max()/sd, n_spike55=int(np.sum(w>mu+5.5*sd)),
            frac_bin0=hist[0]/len(w), faixa_max_sobre_mediana=vmax/np.median(v),
            assimetria=skew(w), curtose=kurtosis(w), media=w.mean(), mediana=np.median(w), sd=sd, mu=mu))
    return out
jobs=[(r.run_id,r.rtt_path,False) for r in neg.itertuples()]+[(r.run_id,r.rtt_path,True) for r in pos.itertuples()]
with Pool(10) as p: res=p.map(diag,jobs,chunksize=4)
w=pd.DataFrame([x for l in res for x in l]); w.to_csv(D+"resultados/T16_diagnostico_metodos_janelas.csv.gz",index=False,compression="gzip")
print("janelas:",w.groupby("ataque").size().to_dict())
