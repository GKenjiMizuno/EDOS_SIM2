import subprocess
import os
import shutil

# Script temporario, sem sudo. Objetivo: encontrar o valor de WU (custo por
# requisicao de ataque) onde as execucoes comecam a apresentar MUITOS erros
# de requisicao (deixam de ser um ataque "discreto" e passam a causar falha
# real / efeito tipo DDoS). Dados de hoje ja mostraram, em rps=10/att=4:
# WU=100000 -> 0 erros; WU=200000 -> 1747 erros. A transicao esta nesse
# intervalo -- varredura fina + repeticoes.

WU_VALUES = [100000, 125000, 150000, 175000, 200000, 250000, 300000]
REPS = 2
RPS_PER_ATTACKER = 10   # mesmo ponto "pior caso" ja caracterizado hoje
NUM_ATTACKERS = 4
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/wu_calibration"
os.makedirs(RESULTS_DIR, exist_ok=True)

for wu in WU_VALUES:
    for rep in range(1, REPS + 1):
        print(f"\n===== Limiar de erro: WU={wu} (rps={RPS_PER_ATTACKER}, att=4) — "
              f"repetição {rep}/{REPS} =====", flush=True)
        cmd = [
            "python3", "main_orchestrator.py",
            "--rps", str(RPS_PER_ATTACKER),
            "--attackers", str(NUM_ATTACKERS),
            "--work-units", str(wu),
            "--duration", str(SIMULATION_DURATION),
        ]
        subprocess.run(cmd)

        metrics_filename = f"metrics_rps{RPS_PER_ATTACKER}_att4_WU{wu}_errthr_rep{rep}.csv"
        shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, metrics_filename))

        attack_summary_src = "attack_summary_log.csv"
        if os.path.exists(attack_summary_src):
            attack_summary_filename = f"attack_summary_log_{RPS_PER_ATTACKER}_4_WU{wu}_errthr_rep{rep}.csv"
            shutil.move(attack_summary_src, os.path.join(RESULTS_DIR, attack_summary_filename))

        rtt_log_src = "rtt_log.csv"
        if os.path.exists(rtt_log_src):
            rtt_log_filename = f"rtt_log_rps{RPS_PER_ATTACKER}_att4_WU{wu}_errthr_rep{rep}.csv"
            shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, rtt_log_filename))

        traffic_capture_src = "traffic_capture.csv"
        if os.path.exists(traffic_capture_src):
            traffic_capture_filename = f"traffic_capture_rps{RPS_PER_ATTACKER}_att4_WU{wu}_errthr_rep{rep}.csv"
            shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, traffic_capture_filename))

print("\nVarredura de limiar de erro concluída.", flush=True)
