import subprocess
import os
import shutil

# Script temporario, nao roda sudo (nao precisa mais, ver RESUMO_MADRUGADA).
# Objetivo: encontrar o limiar real de capacidade do baseline normal (WU=10)
# com granularidade fina + repeticoes, em vez de uma amostra so por ponto.
# Dados de hoje ja mostraram: 200 agregado = estavel (1 amostra, 52.8% pico),
# 250 agregado = instavel (3 repeticoes, 65.8-69.3% pico, todas cruzam 60%).
# Entao a transicao real esta entre 200 e 250 -- varredura fina nessa faixa.

AGGREGATE_RPS_VALUES = [200, 210, 220, 230, 240, 250]
REPS = 3  # 2->3: achado da tarde (12/08) mostrou desvio de até 17 pontos
          # percentuais entre repeticoes do mesmo ponto (300 agregado) --
          # 2 reps nao e suficiente pra confiar no limiar encontrado aqui.
NORMAL_WORK_UNITS = 10
NORMAL_NUM_CLIENTS = 4
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

for agg in AGGREGATE_RPS_VALUES:
    rps_per_client = agg / NORMAL_NUM_CLIENTS
    for rep in range(1, REPS + 1):
        print(f"\n===== Limiar: {agg} agregado (WU=10) — repetição {rep}/{REPS} =====", flush=True)
        cmd = [
            "python3", "main_orchestrator.py",
            "--normal-rps", str(rps_per_client),
            "--normal-work-units", str(NORMAL_WORK_UNITS),
            "--attack-duration", "0",
            "--duration", str(SIMULATION_DURATION),
        ]
        subprocess.run(cmd)

        metrics_filename = f"metrics_normal_rps{rps_per_client}_WU10_thr_agg{agg}_rep{rep}.csv"
        shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, metrics_filename))

        traffic_capture_src = "traffic_capture.csv"
        if os.path.exists(traffic_capture_src):
            traffic_capture_filename = f"traffic_capture_normal_thr_agg{agg}_rep{rep}.csv"
            shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, traffic_capture_filename))

        # rtt_log.csv e normal_traffic_summary_log.csv nao eram salvos aqui
        # (script escrito antes desses dois fixes -- ver changes.txt). Agora
        # que existem, salvar tambem: taxa de erro do trafego normal e
        # diretamente relevante pra decidir o limiar (teto de vazao
        # descoberto na sessao 12/08 tarde).
        rtt_log_src = "rtt_log.csv"
        if os.path.exists(rtt_log_src):
            rtt_log_filename = f"rtt_log_normal_thr_agg{agg}_rep{rep}.csv"
            shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, rtt_log_filename))

        normal_summary_src = "normal_traffic_summary_log.csv"
        if os.path.exists(normal_summary_src):
            normal_summary_filename = f"normal_traffic_summary_log_thr_agg{agg}_rep{rep}.csv"
            shutil.move(normal_summary_src, os.path.join(RESULTS_DIR, normal_summary_filename))

        attack_summary_src = "attack_summary_log.csv"
        if os.path.exists(attack_summary_src):
            os.remove(attack_summary_src)

print("\nVarredura de limiar concluída.", flush=True)
