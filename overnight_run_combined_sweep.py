import subprocess
import os
import shutil

# Script temporario (nao faz parte do fluxo permanente): espelha
# run_experiments_combined.py exatamente (mesmos NORMAL_SCENARIOS,
# intensidades, WU, convencao de nome de arquivo), mas SEM o prefixo "sudo"
# na chamada do main_orchestrator.py. Existe so porque, depois do
# `setcap cap_net_raw,cap_net_admin=eip` aplicado ao tcpdump nesta sessao,
# o simulador inteiro (Docker + tcpdump) roda sem privilegios elevados —
# mas run_experiments_combined.py ainda tem "sudo" fixo no proprio codigo,
# e a instrucao desta sessao foi rodar os testes SEM alterar nenhum
# arquivo existente. Este script evita editar o original enquanto ainda
# completa a varredura pendente (seção 30/31 do changes.txt). Se o "sudo"
# for removido de run_experiments_combined.py no futuro (mudança de
# código real, precisa de aprovação), este arquivo pode ser apagado.

NORMAL_SCENARIOS = {
    "S1": 40,
    "S2": 100,
    "S3": 200,
    "S4": 300,
}
ATTACK_INTENSITIES_PCT = [1, 5, 10]
ATTACK_WORK_UNITS_LIST = [300000, 500000]

NORMAL_NUM_CLIENTS = 4
ATTACK_NUM_ATTACKERS = 4
NORMAL_WORK_UNITS = 10
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/combined_sweep"
os.makedirs(RESULTS_DIR, exist_ok=True)

for scenario_name, normal_aggregate_rps in NORMAL_SCENARIOS.items():
    for pct in ATTACK_INTENSITIES_PCT:
        for work_units in ATTACK_WORK_UNITS_LIST:
            attack_aggregate_rps = normal_aggregate_rps * pct / 100.0
            normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
            attack_rps_per_attacker = attack_aggregate_rps / ATTACK_NUM_ATTACKERS

            print(f"\n===== {scenario_name} ({normal_aggregate_rps} req/s normal) + {pct}% ataque "
                  f"(~{attack_aggregate_rps:.2f} req/s) @ WU={work_units} =====", flush=True)

            cmd = [
                "python3",
                "main_orchestrator.py",
                "--normal-rps", str(normal_rps_per_client),
                "--rps", str(attack_rps_per_attacker),
                "--attackers", str(ATTACK_NUM_ATTACKERS),
                "--work-units", str(work_units),
                "--normal-work-units", str(NORMAL_WORK_UNITS),
                "--duration", str(SIMULATION_DURATION),
            ]
            subprocess.run(cmd)

            metrics_filename = f"metrics_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, metrics_filename))

            attack_summary_src = "attack_summary_log.csv"
            attack_summary_filename = f"attack_summary_log_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            if os.path.exists(attack_summary_src):
                shutil.move(attack_summary_src, os.path.join(RESULTS_DIR, attack_summary_filename))
            else:
                print(f"[WARNING] {attack_summary_src} não encontrado.")

            rtt_log_src = "rtt_log.csv"
            rtt_log_filename = f"rtt_log_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            if os.path.exists(rtt_log_src):
                shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, rtt_log_filename))
            else:
                print(f"[WARNING] {rtt_log_src} não encontrado.")

            traffic_capture_src = "traffic_capture.csv"
            traffic_capture_filename = f"traffic_capture_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            if os.path.exists(traffic_capture_src):
                shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, traffic_capture_filename))
            else:
                print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nAll combined experiments completed.", flush=True)
