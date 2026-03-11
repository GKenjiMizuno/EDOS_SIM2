import subprocess
import itertools
import os
import shutil
from datetime import datetime

RPS_VALUES = [2, 4, 8, 16]
ATTACKERS_VALUES = [1, 2, 4]

RESULTS_DIR = "experiment_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, attackers in itertools.product(RPS_VALUES, ATTACKERS_VALUES):

    print(f"\n===== Running Experiment RPS={rps}, ATTACKERS={attackers} =====")

    cmd = [
        "sudo",
        "python3",
        "main_orchestrator.py",
        "--rps", str(rps),
        "--attackers", str(attackers),
        "--duration", "120"
    ]

    subprocess.run(cmd)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    new_filename = f"metrics_rps{rps}_att{attackers}.csv"
    shutil.move("simulation_metrics.csv",
                os.path.join(RESULTS_DIR, new_filename))

print("\nAll experiments completed.")