import subprocess
import itertools
import os
import shutil
from datetime import datetime

RPS_VALUES = [1,5,10]
ATTACKERS_VALUES = [4]
WORK_UNITS_VALUES = [5000, 20000, 50000, 100000]

RESULTS_DIR = "experiment_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, attackers, work_units in itertools.product(RPS_VALUES, ATTACKERS_VALUES, WORK_UNITS_VALUES):

    print(f"\n===== Running Experiment RPS={rps}, ATTACKERS={attackers}, WORK_UNITS={work_units} =====")

    cmd = [
        "sudo",
        "python3",
        "main_orchestrator.py",
        "--rps", str(rps),
        "--attackers", str(attackers),
        "--work-units", str(work_units),
        "--duration", "180"
    ]

    subprocess.run(cmd)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # =========================
    # Metrics log
    # =========================
    metrics_filename = (
        f"metrics_rps{rps}_att{attackers}_WU{work_units}.csv"
    )

    shutil.move(
        "simulation_metrics.csv",
        os.path.join(RESULTS_DIR, metrics_filename)
    )

        # =========================
    # Attack summary log
    # =========================
    attack_summary_src = "attack_summary_log.csv"
    attack_summary_filename = f"attack_summary_log_{rps}_{attackers}_WU{work_units}.csv"
    attack_summary_dst = os.path.join(RESULTS_DIR, attack_summary_filename)

    if os.path.exists(attack_summary_src):
        shutil.move(attack_summary_src, attack_summary_dst)
    else:
        print(f"[WARNING] {attack_summary_src} não encontrado.")

print("\nAll experiments completed.")