import glob
import os
import re
import statistics as stats

import pandas as pd

# Script de analise estatistica overnight (nao roda simulacoes, so le CSVs ja
# coletados). Nao faz parte do fluxo permanente do projeto -- criado pra
# consolidar a analise pedida (reproducibilidade, variancia, achados) numa
# unica passada, em vez de comandos ad-hoc espalhados.

NB = "experiment_results/normal_baseline"
WC = "experiment_results/wu_calibration"
CS = "experiment_results/combined_sweep"


def load_metrics(path):
    df = pd.read_csv(path)
    return df


def summarize(df):
    from collections import Counter
    decisions = Counter(df['decision'])
    return dict(
        peak_cpu=round(df['average_cpu_percent'].max(), 1),
        avg_cpu=round(df['average_cpu_percent'].mean(), 1),
        max_inst=int(df['num_instances'].max()),
        scaleups=int(decisions.get('SCALE_UP', 0)),
        scaledowns=int(decisions.get('SCALE_DOWN', 0)),
    )


print("=" * 80)
print("1) NORMAL_BASELINE - reproducibilidade nos pontos com repeticao real")
print("=" * 80)

# Ponto S4 candidato 300 (medido 2x em momentos diferentes: recalibracao
# original em 10/08 e reexecucao pos-fix em 11/08) + candidato 250 (3 reps
# de verdade, mesma execucao).
rps75_path = os.path.join(NB, "metrics_normal_rps75_WU10.csv")
if os.path.exists(rps75_path):
    s = summarize(load_metrics(rps75_path))
    print(f"\nS4 candidato = 300 agregado, WU=10 (unica amostra pos-fix atual):")
    print(f"  peak_cpu={s['peak_cpu']}%  avg_cpu={s['avg_cpu']}%  scaleups={s['scaleups']}  max_inst={s['max_inst']}")
    print("  (comparar com a amostra anterior registrada na sessao: peak 53.6%/avg 41.1%/0 scaleups,")
    print("   e com a reexecucao que deu peak 87.9%/avg 47.9%/3 scaleups -- 3 amostras da MESMA config,")
    print("   3 resultados qualitativamente diferentes)")

rep_paths = sorted(glob.glob(os.path.join(NB, "metrics_normal_rps62.5_WU10_rep*.csv")))
if rep_paths:
    peak_cpus, avg_cpus, scaleup_counts = [], [], []
    print(f"\nS4 candidato = 250 agregado, WU=10 ({len(rep_paths)} repeticoes reais):")
    for p in rep_paths:
        s = summarize(load_metrics(p))
        peak_cpus.append(s['peak_cpu'])
        avg_cpus.append(s['avg_cpu'])
        scaleup_counts.append(s['scaleups'])
        print(f"  {os.path.basename(p)}: peak_cpu={s['peak_cpu']}%  avg_cpu={s['avg_cpu']}%  scaleups={s['scaleups']}")
    if len(peak_cpus) >= 2:
        print(f"  --> peak_cpu: media={stats.mean(peak_cpus):.1f}%  desvio={stats.stdev(peak_cpus):.1f}%"
              f"  min={min(peak_cpus):.1f}%  max={max(peak_cpus):.1f}%")
        print(f"  --> avg_cpu:  media={stats.mean(avg_cpus):.1f}%  desvio={stats.stdev(avg_cpus):.1f}%")
        print(f"  --> scale-ups em TODAS as {len(scaleup_counts)} repeticoes: {scaleup_counts}"
              f" (limiar de scale-up = 60%)")

print("\n" + "=" * 80)
print("2) NORMAL_BASELINE - pontos originais (1 amostra cada, sem repeticao)")
print("=" * 80)
for f in sorted(glob.glob(os.path.join(NB, "metrics_normal_rps[0-9]*_WU*.csv"))):
    name = os.path.basename(f)
    if "rep" in name or "rps75" in name or "rps62" in name:
        continue
    m = re.match(r"metrics_normal_rps(\d+)_WU(\d+)\.csv", name)
    if not m:
        continue
    rps, wu = m.group(1), m.group(2)
    s = summarize(load_metrics(f))
    agg = int(rps) * 4
    print(f"  agg={agg:>4d} WU={wu:>5s}: peak_cpu={s['peak_cpu']:>6.1f}%  avg_cpu={s['avg_cpu']:>5.1f}%  "
          f"scaleups={s['scaleups']}  max_inst={s['max_inst']}")

print("\n" + "=" * 80)
print("3) WU_CALIBRATION - estado atual (pos-fix, 11/08) + bursts detectados")
print("=" * 80)
for f in sorted(glob.glob(os.path.join(WC, "metrics_rps*_att4_WU*.csv"))):
    name = os.path.basename(f)
    m = re.match(r"metrics_rps(\d+)_att4_WU(\d+)\.csv", name)
    rps, wu = m.group(1), m.group(2)
    s = summarize(load_metrics(f))
    xlsx = os.path.join(WC, f"rtt_bursts_rps{rps}_att4_WU{wu}.xlsx")
    bursts = total = None
    if os.path.exists(xlsx):
        bdf = pd.read_excel(xlsx)
        bursts = int((bdf['Status Burst'] == 'DDoS Burst').sum())
        total = len(bdf)
    errs = None
    asum = os.path.join(WC, f"attack_summary_log_{rps}_4_WU{wu}.csv")
    if os.path.exists(asum):
        adf = pd.read_csv(asum)
        errs = int(pd.to_numeric(adf['errors'], errors='coerce').sum())
    print(f"  rps={rps:>2s} WU={wu:>6s}: peak_cpu={s['peak_cpu']:>6.1f}%  avg_cpu={s['avg_cpu']:>5.1f}%  "
          f"scaleups={s['scaleups']}  bursts={bursts}/{total}  errors={errs}")

print("\n" + "=" * 80)
print("4) COMBINED_SWEEP - estado atual dos arquivos (ainda pre-fix se nao regenerado)")
print("=" * 80)
cs_files = sorted(glob.glob(os.path.join(CS, "metrics_S*.csv")))
print(f"Total de arquivos metrics_S*.csv encontrados: {len(cs_files)}")
if cs_files:
    import datetime
    mtimes = [os.path.getmtime(f) for f in cs_files]
    oldest = datetime.datetime.fromtimestamp(min(mtimes))
    newest = datetime.datetime.fromtimestamp(max(mtimes))
    print(f"Mtime mais antigo: {oldest}   Mtime mais novo: {newest}")
    print("(se ambos forem de 10/08, os dados ainda sao pre-fix e serao sobrescritos")
    print(" pela regeneracao rodando em background nesta mesma noite)")

print("\nFim da analise.")
