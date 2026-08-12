import subprocess
import itertools
import os
import shutil

# Varredura irmã de run_experiments.py, mas SEM ataque: caracteriza o
# comportamento de CPU/RTT do servidor sob tráfego normal em várias
# intensidades, servindo de baseline de comparação para a varredura de ataque.
NORMAL_RPS_VALUES = [10, 25, 50, 100]
NORMAL_WORK_UNITS_VALUES = [10, 100, 1000, 5000]

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, work_units in itertools.product(NORMAL_RPS_VALUES, NORMAL_WORK_UNITS_VALUES):

    print(f"\n===== Running Normal-Only Experiment RPS={rps}, WORK_UNITS={work_units} =====")

    cmd = [
        "sudo",
        "python3",
        "main_orchestrator.py",
        "--normal-rps", str(rps),
        "--normal-work-units", str(work_units),
        "--attack-duration", "0",
        "--duration", "180"
    ]

    subprocess.run(cmd)

    # =========================
    # Metrics log
    # =========================
    metrics_filename = f"metrics_normal_rps{rps}_WU{work_units}.csv"

    shutil.move(
        "simulation_metrics.csv",
        os.path.join(RESULTS_DIR, metrics_filename)
    )

    # =========================
    # Attack summary log
    # =========================
    # Sempre criado (só com cabeçalho) por attack_summary_logger.init_attack_summary_log(),
    # mesmo sem ataque. Sem dados úteis neste modo, então é descartado em vez
    # de salvo, para não poluir experiment_results/ com arquivos vazios.
    attack_summary_src = "attack_summary_log.csv"
    if os.path.exists(attack_summary_src):
        os.remove(attack_summary_src)

    # =========================
    # Traffic capture (tcpdump)
    # =========================
    traffic_capture_src = "traffic_capture.csv"
    traffic_capture_filename = f"traffic_capture_normal_rps{rps}_WU{work_units}.csv"
    traffic_capture_dst = os.path.join(RESULTS_DIR, traffic_capture_filename)

    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, traffic_capture_dst)
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nAll normal-traffic experiments completed.")
