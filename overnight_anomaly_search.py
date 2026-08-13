import glob
import os
import re
from collections import Counter

import pandas as pd

# Script temporario de busca sistematica por anomalias em experiment_results/.
# Roda depois que os dados (normal_baseline, wu_calibration, combined_sweep)
# ja estao no lugar. Nao altera nenhum CSV, so le e reporta.

CS = "experiment_results/combined_sweep"


def scan_combined_sweep():
    rows = []
    for f in sorted(glob.glob(os.path.join(CS, "metrics_S*.csv"))):
        name = os.path.basename(f)
        m = re.match(r"metrics_(S\d)_atk(\d+)pct_wu(\d+)\.csv", name)
        if not m:
            continue
        scenario, pct, wu = m.group(1), int(m.group(2)), int(m.group(3))
        df = pd.read_csv(f)
        decisions = Counter(df['decision'])
        zero_rtt = int((df['avg_rtt_ms'].iloc[2:] == 0.0).sum())

        asum_path = os.path.join(CS, f"attack_summary_log_{scenario}_atk{pct}pct_wu{wu}.csv")
        errs = 0
        if os.path.exists(asum_path):
            adf = pd.read_csv(asum_path)
            errs = int(pd.to_numeric(adf['errors'], errors='coerce').sum())

        xlsx_path = os.path.join(CS, f"rtt_bursts_{scenario}_atk{pct}pct_wu{wu}.xlsx")
        bursts = total_windows = None
        if os.path.exists(xlsx_path):
            bdf = pd.read_excel(xlsx_path)
            bursts = int((bdf['Status Burst'] == 'DDoS Burst').sum())
            total_windows = len(bdf)

        rows.append(dict(
            scenario=scenario, pct=pct, wu=wu,
            peak_cpu=round(df['average_cpu_percent'].max(), 1),
            avg_cpu=round(df['average_cpu_percent'].mean(), 1),
            scaleups=int(decisions.get('SCALE_UP', 0)),
            max_inst=int(df['num_instances'].max()),
            zero_rtt_windows=zero_rtt,
            errors=errs,
            bursts=bursts,
            total_windows=total_windows,
            mtime=os.path.getmtime(f),
        ))
    return pd.DataFrame(rows)


def main():
    df = scan_combined_sweep()
    if df.empty:
        print("Nenhum dado em combined_sweep encontrado.")
        return

    print(f"Total de execuções analisadas: {len(df)}\n")

    print("=" * 80)
    print("ANOMALIA 1: monotonicidade quebrada (scenario/intensidade maior deveria")
    print("            geralmente causar efeito >= o de um scenario/intensidade menor)")
    print("=" * 80)
    for wu in sorted(df['wu'].unique()):
        sub = df[df.wu == wu].copy()
        sub['scenario_rank'] = sub['scenario'].map({'S1': 1, 'S2': 2, 'S3': 3, 'S4': 4})
        for pct in sorted(sub['pct'].unique()):
            row = sub[sub.pct == pct].sort_values('scenario_rank')
            errs = row['errors'].tolist()
            scenarios = row['scenario'].tolist()
            for i in range(1, len(errs)):
                if errs[i] < errs[i-1] * 0.5 and errs[i-1] > 50:
                    print(f"  WU={wu} pct={pct}%: erros caem de {scenarios[i-1]}={errs[i-1]} "
                          f"para {scenarios[i]}={errs[i]} (queda >50%% apesar de cenário maior)")

    print("\n" + "=" * 80)
    print("ANOMALIA 2: janelas com cobertura muito baixa (poucas amostras de RTT)")
    print("=" * 80)
    typical = df['total_windows'].median()
    for _, r in df.iterrows():
        if r['total_windows'] is not None and r['total_windows'] < typical * 0.6:
            print(f"  {r['scenario']}/{r['pct']}%/WU{r['wu']}: só {int(r['total_windows'])} janelas "
                  f"analisáveis (típico ~{typical:.0f}) -- erros={r['errors']}, zero_rtt_windows={r['zero_rtt_windows']}")

    print("\n" + "=" * 80)
    print("ANOMALIA 3: execuções com erros de requisição > 100 (deixaram de ser 'discretas')")
    print("=" * 80)
    severe = df[df['errors'] > 100].sort_values('errors', ascending=False)
    for _, r in severe.iterrows():
        print(f"  {r['scenario']}/{r['pct']}%/WU{r['wu']}: {int(r['errors'])} erros, "
              f"peak_cpu={r['peak_cpu']}%, bursts={r['bursts']}/{r['total_windows']}")

    print("\n" + "=" * 80)
    print("ANOMALIA 4: scale-up sem NENHUM erro apesar de CPU pico > 150%")
    print("=" * 80)
    weird = df[(df['peak_cpu'] > 150) & (df['errors'] == 0)]
    for _, r in weird.iterrows():
        print(f"  {r['scenario']}/{r['pct']}%/WU{r['wu']}: peak_cpu={r['peak_cpu']}% mas 0 erros "
              f"(scaleups={r['scaleups']})")

    print("\nFim da busca de anomalias.")
    return df


if __name__ == "__main__":
    main()
