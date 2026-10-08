"""
Complemento do §129 (calibracao_parametros_detectores.py): CUSUM e média
avaliados CONTINUAMENTE (CUSUM a cada requisição; média móvel de 10 s a cada
1 s), no tempo corrigido dos saltos de relógio do WSL2 (§128).
Parte 1: latência do 1º alarme vs 1º SCALE_UP nas execuções com dano ->
  resultados/T18e_latencia_continua.csv
Parte 2: alarme falso nas execuções sem ataque (WU=10, <=640 rps), t=20-160 s
  -> resultados/T18f_fpr_continuo.csv
"""
import numpy as np
import pandas as pd

t = pd.read_csv("experiment_results/deteccao_pos_lb/resultados/execucoes_avaliadas.csv")
gil = t.gil.fillna(False).astype(bool)
ok = (t.atk_ini.sub(20).abs() < 1) & (t.atk_fim.sub(160).abs() < 2)
d = t[t.ataque & ~gil & ok & t.escalou_no_ataque].copy()
rows = []
for _, r in d.iterrows():
    m = pd.read_csv(r.metrics_path)
    su = m[(m.decision == "SCALE_UP") & (m.elapsed_time_s > 20)].elapsed_time_s.min()
    x = pd.read_csv(r.rtt_path).sort_values("timestamp")
    tt = (x.timestamp - x.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0]); tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    v = x.rtt.values; b = v[tt < 20]; mu, sd = b.mean(), b.std()
    c = 0.0; cs = np.empty(len(v))
    for i, y in enumerate(v):
        c = max(0.0, c + (y - mu) - 0.5 * sd); cs[i] = c
    cs /= sd
    row = dict(run=r.run_id, su=su)
    for h in (1000, 2000, 5000):
        k = np.argmax(cs > h); row[f"cusum{h}"] = tt[k] if cs[k] > h else np.nan
    # média móvel dos últimos 10 s avaliada a cada 1 s
    s = pd.Series(v, index=pd.to_timedelta(tt, unit="s")).rolling("10s").mean()
    s1 = s.resample("1s").last()
    for rr in (1.5, 1.8):
        al = s1[(s1 > rr * mu) & (s1.index.total_seconds() >= 20)]
        row[f"media{rr}"] = al.index[0].total_seconds() + 1 if len(al) else np.nan
    rows.append(row)
L = pd.DataFrame(rows)
print("n execuções com dano:", len(L), "| 1º SCALE_UP mediano:", L.su.median(), "| quartis", L.su.quantile([.25, .75]).tolist())
for c in [c for c in L if c not in ("run", "su")]:
    print(f"{c:10s} alarme mediano {L[c].median():6.1f} s | antes do SCALE_UP: {100*(L[c] < L.su).mean():5.1f}% | folga mediana {(L.su - L[c]).median():6.1f} s")
L.to_csv("experiment_results/deteccao_pos_lb/resultados/T18e_latencia_continua.csv", index=False)

# ---------------------------------------------------------------- parte 2
n = t[~t.ataque & (t.normal_nom <= 640) & (t.normal_wu == 10) & ~t.captura.astype(bool)].copy()
rows = []
for _, r in n.iterrows():
    x = pd.read_csv(r.rtt_path).sort_values("timestamp")
    tt = (x.timestamp - x.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0]); tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    v = x.rtt.values; b = v[tt < 20]; mu, sd = b.mean(), b.std()
    c = 0.0; cs = np.empty(len(v))
    for i, y in enumerate(v):
        c = max(0.0, c + (y - mu) - 0.5 * sd); cs[i] = c
    cs /= sd
    janela = (tt >= 20) & (tt <= 160)
    s = pd.Series(v, index=pd.to_timedelta(tt, unit="s")).rolling("10s").mean().resample("1s").last()
    s = s[(s.index.total_seconds() >= 20) & (s.index.total_seconds() <= 160)]
    rows.append(dict(run=r.run_id, carga=r.normal_nom, rep=r.rep, cmax=cs[janela].max() if janela.any() else 0,
                     rmax=(s / mu).max()))
F = pd.DataFrame(rows)
F["faixa"] = pd.cut(F.carga, [0, 25, 50, 100, 200, 350, 640], labels=["16-25", "32-50", "64-100", "128-200", "210-350", "400-640"])
F.to_csv("experiment_results/deteccao_pos_lb/resultados/T18f_fpr_continuo.csv", index=False)
print("n NEG:", len(F))
for h in (1000, 2000, 5000, 10000, 20000):
    print(f"CUSUM contínuo {h:>6}σ: FPR {100*(F.cmax>h).mean():5.1f}% |", (100*(F.cmax>h)).groupby(F.faixa, observed=True).mean().round(1).to_dict())
for rr in (1.5, 1.8, 2.0, 2.5):
    print(f"média 10 s contínua > {rr}x: FPR {100*(F.rmax>rr).mean():5.1f}% |", (100*(F.rmax>rr)).groupby(F.faixa, observed=True).mean().round(1).to_dict())
