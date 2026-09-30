"""
Tráfego normal isolado pros agregados novos usados em S9-S11
(run_atacantes_intensidade_grid_s9_s11.py) -- 1280 e 2560 rps agregado.

640 rps (S9) NÃO entra aqui: já é coberto pelo lote de "faltantes"
(run_unaffected_rerun.py), que recoleta o único rep de agg=640 que ainda
estava com dado pré-correção -- depois desse lote, agg=640 fica com 10/10
reps 100% pós-correção (9 já recoletadas antes + 1 desse lote), sem precisar
de execução nova aqui.

Mesma convenção de nome da família "pow2 base 20" (normal_baseline/,
gráficos 23/42/57): normal_agg{agg}_WU10_refined_rep{N}, NORMAL_NUM_CLIENTS
fixo em 4 (mesma fórmula usada por jobs_normal_baseline em
run_scaling_affected_rerun.py, reaproveitado via import).

5 repetições cada (padrão adotado no resto do dataset pós load balancer,
não as 10 usadas nos agregados mais antigos da mesma família).

Uso:
  python3 run_normal_isolado_s9_s11.py --dry-run
  python3 run_normal_isolado_s9_s11.py
"""
import argparse

import run_scaling_affected_rerun as base

AGGREGATE_TARGETS = [1280, 2560]
NORMAL_NUM_CLIENTS = 4
NORMAL_WORK_UNITS = 10
NUM_REPS = 5
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/normal_baseline"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = len(AGGREGATE_TARGETS) * NUM_REPS
    i = 0
    for agg in AGGREGATE_TARGETS:
        rps_per_client = agg / NORMAL_NUM_CLIENTS
        for rep in range(1, NUM_REPS + 1):
            i += 1
            suffix = f"normal_agg{agg}_WU{NORMAL_WORK_UNITS}_refined_rep{rep}"
            if args.dry_run:
                print(f"[DRY-RUN] [{i}/{total}] {suffix}  (agg={agg}, "
                      f"rps/cliente={rps_per_client})")
                continue
            print(f"\n[{i}/{total}] {suffix}", flush=True)
            cmd_args = [
                "--normal-rps", str(rps_per_client),
                "--normal-work-units", str(NORMAL_WORK_UNITS),
                "--attack-duration", "0",
                "--duration", str(SIMULATION_DURATION),
            ]
            base.backup_existing(RESULTS_DIR, suffix)  # no-op esperado (arquivo novo)
            base.run_and_collect(cmd_args, RESULTS_DIR, suffix,
                                  save_attack_summary=False, save_normal_summary=True)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}normal isolado (S9-S11, só agregados novos): "
          f"{total} execuções" + (" planejadas" if args.dry_run else " concluídas"))


if __name__ == "__main__":
    main()
