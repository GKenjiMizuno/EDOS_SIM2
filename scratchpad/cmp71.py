import numpy as np, pandas as pd
from EntCusumZV3 import (bordas_log_baseline, histograma_faixas, divergencia_js,
                         z_robusto_params, Z_K_RECOMENDADO, Z_FRAC_RECOMENDADA,
                         ENTROPIA_BINS_RECOMENDADO, ENTROPIA_JS_RECOMENDADO)
H, RAZAO = 1000.0, 1.8

def corrige_t(r):
    r = r.sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    return tt, r.rtt.values

def analisa(path_rtt, path_m, base_fim, a0, a1, tag):
    tt, v = corrige_t(pd.read_csv(path_rtt))
    b = v[tt < base_fim]
    mu, sd = b.mean(), b.std()
    # CUSUM com reset
    c = 0.0
    z_med, z_esc = z_robusto_params(b)
    bordas = bordas_log_baseline(b, ENTROPIA_BINS_RECOMENDADO)
    p_base = histograma_faixas(b, bordas)
    cus_al = z_al = e_al = comb_al = 0; nj = 0
    cus_run = np.empty(len(v))
    cc = 0.0
    for i, x in enumerate(v):
        cc = max(0.0, cc + (x - mu) - 0.5*sd)
        if cc > H*sd:   # reset
            cc = 0.0
        cus_run[i] = cc
    # janelas de 20s, passo 10, no ataque
    for t0 in np.arange(a0, a1-19.999, 10):
        m = (tt >= t0) & (tt < t0+20)
        if m.sum() < 10: continue
        nj += 1
        w = v[m]
        cs = cus_run[np.where(m)[0][-1]]  # sem reset-aware aqui, aproximação
        # detecção por reset: olhar se algum ponto na janela disparou
        # recomputar disparo
        media_alta = w.mean() > RAZAO*mu
        z_frac = float(((w - z_med)/z_esc > Z_K_RECOMENDADO).mean())
        z_d = z_frac > Z_FRAC_RECOMENDADA
        e_d = divergencia_js(histograma_faixas(w, bordas), p_base) > ENTROPIA_JS_RECOMENDADO
        c_d = cs > H*sd
        cus_al += c_d; z_al += z_d; e_al += e_d
        comb_al += (media_alta and (z_d or c_d))
    m = pd.read_csv(path_m)
    rtt_atk = v[(tt>=a0)&(tt<a1)]
    print(f"\n[{tag}]")
    print(f"  baseline t<{base_fim}: n={len(b)}  mu={mu:.2f}ms  sd={sd:.2f}ms  "
          f"CUSUM h=1000σ={H*sd:.0f}ms  floor 1.8x={RAZAO*mu:.2f}ms")
    print(f"  RTT no ataque ({a0}-{a1}s): media={rtt_atk.mean():.2f}ms  mediana={np.median(rtt_atk):.2f}ms  "
          f"p95={np.percentile(rtt_atk,95):.1f}ms  max={rtt_atk.max():.0f}ms")
    print(f"  CPU pico={m.average_cpu_percent.max():.1f}%  inst_max={int(m.num_instances.max())}")
    print(f"  janelas no ataque={nj}:  CUSUM {cus_al}/{nj}  Z {z_al}/{nj}  ent {e_al}/{nj}  comb {comb_al}/{nj}")

# ANTIGO (gráfico 71): confirmacao_320, baseline t<20, ataque 20-160
for rep in (1,2,3):
    s=f"agg320_nwu10000_atk5pct_awu200000_rep{rep}"
    analisa(f"experiment_results/confirmacao_320/rtt_log_{s}.csv",
            f"experiment_results/confirmacao_320/metrics_{s}.csv", 20, 20, 160, f"ANTIGO graf71 rep{rep}")
# NOVO: edos_furtivo_wu, baseline t<60, ataque 60-180
s="agg320_nwu10000_atk5pct_awu200000_rep1"
analisa(f"experiment_results/edos_furtivo_wu/rtt_log_{s}.csv",
        f"experiment_results/edos_furtivo_wu/metrics_{s}.csv", 60, 60, 180, "NOVO bateria rep1")
