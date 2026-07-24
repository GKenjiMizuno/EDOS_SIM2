import subprocess
import itertools
import os
import shutil

# Varredura combinada (Tabela 5, Sotelo Monge et al.): para cada cenário de
# tráfego normal (Tabela 4), sobrepõe tráfego de ataque como uma porcentagem
# do volume total de requisições normais daquele cenário.
NORMAL_SCENARIOS = {
    "S1": 50,
    "S2": 60,
    "S3": 70,
    "S4": 80,
}
ATTACK_INTENSITIES_PCT = [1, 5, 10]

NORMAL_NUM_CLIENTS = 4      # fixo, mesma contagem usada nas outras varreduras
ATTACK_NUM_ATTACKERS = 4    # fixo
ATTACK_WORK_UNITS = 100000  # calibrado nesta sessão (cruza o limiar de scale-up em RPS moderado)
NORMAL_WORK_UNITS = 10
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

for scenario_name, normal_aggregate_rps in NORMAL_SCENARIOS.items():
    for pct in ATTACK_INTENSITIES_PCT:
        # % do volume TOTAL de requisições normais do cenário, convertido para
        # RPS agregado de ataque (a duração se cancela: pct * total_normal_requests / duration == pct * normal_rate).
        attack_aggregate_rps = normal_aggregate_rps * pct / 100.0

        normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
        attack_rps_per_attacker = attack_aggregate_rps / ATTACK_NUM_ATTACKERS

        print(f"\n===== {scenario_name} ({normal_aggregate_rps} req/s normal) + {pct}% ataque (~{attack_aggregate_rps:.2f} req/s) =====")

        cmd = [
            "sudo",
            "python3",
            "main_orchestrator.py",
            "--normal-rps", str(normal_rps_per_client),
            "--rps", str(attack_rps_per_attacker),
            "--attackers", str(ATTACK_NUM_ATTACKERS),
            "--work-units", str(ATTACK_WORK_UNITS),
            "--normal-work-units", str(NORMAL_WORK_UNITS),
            "--duration", str(SIMULATION_DURATION),
        ]

        subprocess.run(cmd)

        # =========================
        # Metrics log
        # =========================
        metrics_filename = f"metrics_{scenario_name}_atk{pct}pct.csv"
        shutil.move(
            "simulation_metrics.csv",
            os.path.join(RESULTS_DIR, metrics_filename)
        )

        # =========================
        # Attack summary log
        # =========================
        attack_summary_src = "attack_summary_log.csv"
        attack_summary_filename = f"attack_summary_log_{scenario_name}_atk{pct}pct.csv"
        attack_summary_dst = os.path.join(RESULTS_DIR, attack_summary_filename)

        if os.path.exists(attack_summary_src):
            shutil.move(attack_summary_src, attack_summary_dst)
        else:
            print(f"[WARNING] {attack_summary_src} não encontrado.")

print("\nAll combined experiments completed.")
