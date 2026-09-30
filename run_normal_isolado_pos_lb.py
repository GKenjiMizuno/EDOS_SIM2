"""
Tráfego normal isolado, 1 execução por agregado, 20 -> 2560 rps (potência de
2 base 20), tudo coletado numa única sessão com o código pós load balancer.

Motivação (changes.txt §114): os dados de tráfego normal isolado existentes
em normal_baseline/ misturam execuções de "regimes" de máquina diferentes --
os runs originais (nunca recoletados) custam ~1,5-3x mais CPU por requisição
que os recoletados, pra mesma carga entregue. Este lote refaz a curva inteira
de uma vez, no mesmo estado de máquina, pra ter uma base consistente.

Diretório próprio (experiment_results/normal_isolado_pos_lb/), não
normal_baseline/: não sobrescreve nem mistura com a família "refined" antiga,
e evita a confusão de convenções de nome já documentada no §112 (todos os
arquivos aqui usam o mesmo suffix, agg{agg}_WU10_rep{N}).

Mesmo desenho da família "refined": HTTP_NORMAL_NUM_CLIENTS=4 fixo (rps por
cliente = agregado/4), WU=10, 180s. Aviso já conhecido (§112): acima de ~800
rps agregado o gerador de tráfego (4 threads Python) não consegue entregar o
nominal -- 1280/2560 vão entregar bem menos que o pedido. O real entregue é
registrado no normal_traffic_summary_log e mostrado nos gráficos.

Uso:
  python3 run_normal_isolado_pos_lb.py --dry-run
  python3 run_normal_isolado_pos_lb.py
"""
import argparse
import os

import run_scaling_affected_rerun as base

AGGREGATE_TARGETS = [20, 40, 80, 160, 320, 640, 1280, 2560]
NORMAL_NUM_CLIENTS = 4
NORMAL_WORK_UNITS = 10
NUM_REPS = 1
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/normal_isolado_pos_lb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    total = len(AGGREGATE_TARGETS) * NUM_REPS
    i = 0
    for agg in AGGREGATE_TARGETS:
        rps_per_client = agg / NORMAL_NUM_CLIENTS
        for rep in range(1, NUM_REPS + 1):
            i += 1
            suffix = f"agg{agg}_WU{NORMAL_WORK_UNITS}_rep{rep}"
            if args.dry_run:
                print(f"[DRY-RUN] [{i}/{total}] {suffix} (rps/cliente={rps_per_client})")
                continue
            print(f"\n===== [{i}/{total}] normal isolado {suffix} "
                  f"(rps/cliente={rps_per_client}) =====", flush=True)
            cmd_args = [
                "--normal-rps", str(rps_per_client),
                "--normal-clients", str(NORMAL_NUM_CLIENTS),
                "--normal-work-units", str(NORMAL_WORK_UNITS),
                "--attack-duration", "0",
                "--duration", str(SIMULATION_DURATION),
            ]
            base.run_and_collect(cmd_args, RESULTS_DIR, suffix,
                                  save_attack_summary=False, save_normal_summary=True)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}normal isolado pós-LB: "
          f"{total} execuções" + (" planejadas" if args.dry_run else " concluídas"), flush=True)


if __name__ == "__main__":
    main()
