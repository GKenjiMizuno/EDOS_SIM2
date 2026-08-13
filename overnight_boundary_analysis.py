import glob
import os
import re
import statistics as stats
from collections import Counter, defaultdict

import pandas as pd

# Script temporario. Consolida a analise dos dois sweeps de fronteira
# (limiar de capacidade do baseline normal, e limiar de erro por WU) rodados
# esta madrugada, com estatistica de verdade (media/desvio/min/max entre
# repeticoes de cada ponto).

NB = "experiment_results/normal_baseline"
WC = "experiment_results/wu_calibration"


def summarize(path):
    df = pd.read_csv(path)
    decisions = Counter(df['decision'])
    return dict(
        peak_cpu=df['average_cpu_percent'].max(),
        avg_cpu=df['average_cpu_percent'].mean(),
        scaleups=int(decisions.get('SCALE_UP', 0)),
    )


print("=" * 90)
print("1) LIMIAR DE CAPACIDADE DO BASELINE NORMAL (WU=10) — varredura fina 200-250")
print("=" * 90)
by_agg = defaultdict(list)
for f in sorted(glob.glob(os.path.join(NB, "metrics_normal_rps*_WU10_thr_agg*_rep*.csv"))):
    name = os.path.basename(f)
    m = re.match(r"metrics_normal_rps[\d.]+_WU10_thr_agg(\d+)_rep(\d+)\.csv", name)
    if not m:
        continue
    agg = int(m.group(1))
    s = summarize(f)
    by_agg[agg].append(s)

first_unstable = None
for agg in sorted(by_agg.keys()):
    samples = by_agg[agg]
    peaks = [s['peak_cpu'] for s in samples]
    scaleups = [s['scaleups'] for s in samples]
    any_scaleup = any(s > 0 for s in scaleups)
    any_over60 = any(p > 60 for p in peaks)
    status = "INSTAVEL" if (any_scaleup or any_over60) else "estavel"
    if status == "INSTAVEL" and first_unstable is None:
        first_unstable = agg
    mean_peak = stats.mean(peaks)
    std_peak = stats.stdev(peaks) if len(peaks) > 1 else 0.0
    print(f"  agg={agg:4d}: n={len(samples)}  peak_cpu média={mean_peak:6.1f}%  "
          f"desvio={std_peak:5.1f}  scale-ups={scaleups}  -> {status}")

if first_unstable:
    print(f"\n>>> Primeiro ponto instável na varredura fina: {first_unstable} agregado.")
    print(f">>> Recomendação: usar o último ponto ESTÁVEL com folga real como limiar/S4.")

print("\n" + "=" * 90)
print("2) LIMIAR DE ERRO POR WU (rps=10, att=4) — varredura fina 100k-300k")
print("=" * 90)
by_wu = defaultdict(list)
for f in sorted(glob.glob(os.path.join(WC, "metrics_rps10_att4_WU*_errthr_rep*.csv"))):
    name = os.path.basename(f)
    m = re.match(r"metrics_rps10_att4_WU(\d+)_errthr_rep(\d+)\.csv", name)
    if not m:
        continue
    wu = int(m.group(1))
    s = summarize(f)

    rep = int(m.group(2))
    asum = os.path.join(WC, f"attack_summary_log_10_4_WU{wu}_errthr_rep{rep}.csv")
    errs = None
    if os.path.exists(asum):
        adf = pd.read_csv(asum)
        errs = int(pd.to_numeric(adf['errors'], errors='coerce').sum())
    s['errors'] = errs
    by_wu[wu].append(s)

first_high_error = None
for wu in sorted(by_wu.keys()):
    samples = by_wu[wu]
    errs = [s['errors'] for s in samples if s['errors'] is not None]
    peaks = [s['peak_cpu'] for s in samples]
    mean_err = stats.mean(errs) if errs else None
    status = "MUITOS ERROS" if (mean_err is not None and mean_err > 100) else "limpo"
    if status == "MUITOS ERROS" and first_high_error is None:
        first_high_error = wu
    print(f"  WU={wu:6d}: n={len(samples)}  erros={errs}  média={mean_err}  "
          f"peak_cpu média={stats.mean(peaks):6.1f}%  -> {status}")

if first_high_error:
    print(f"\n>>> Primeiro WU com muitos erros na varredura fina: {first_high_error}.")
    print(f">>> Recomendação: usar o maior WU ainda 'limpo' como o limite superior")
    print(f">>> de um ataque W-EDoS puro (sem efeito DDoS) nesse nível de RPS.")

print("\nFim da análise de fronteiras.")
