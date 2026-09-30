"""
Extensão do grid atacantes x intensidade (run_atacantes_intensidade_grid.py)
com 3 cenários novos de tráfego normal mais pesado -- pedido do usuário
depois de descobrir (gráfico 57, changes.txt §108) que o teto de capacidade
pós load balancer subiu bem acima do antigo (~205-210 -> estimado ~850-900
req/s agregado). S1-S8 (script original) ficam intocados -- não reescrito,
não reexecutado -- este é um lote adicional, mesmo diretório de resultados
(nome de arquivo já distingue por cenário, sem colisão).

Não duplica a lógica de run_point() -- importa e reusa direto do script
original (tem guarda __main__, seguro de importar).

WORK_UNITS, ATTACKERS_VALUES, INTENSITIES_PCT, SIMULATION_DURATION:
idênticos ao script original, só NUM_REPS sobe de 1 pra 5 (já é o padrão
adotado no resto do dataset desde a recoleta pós load balancer).

Uso:
  python3 run_atacantes_intensidade_grid_s9_s11.py --dry-run
  python3 run_atacantes_intensidade_grid_s9_s11.py
"""
import argparse

import run_atacantes_intensidade_grid as atk_grid

NORMAL_SCENARIOS = {
    "S9": 640,
    "S10": 1280,
    "S11": 2560,
}
ATTACKERS_VALUES = atk_grid.ATTACKERS_VALUES         # [1, 2, 4]
INTENSITIES_PCT = atk_grid.INTENSITIES_PCT           # [1, 5, 10, 15, 20, 25]
NUM_REPS = 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = len(NORMAL_SCENARIOS) * len(ATTACKERS_VALUES) * len(INTENSITIES_PCT) * NUM_REPS
    i = 0
    for scenario_name, agg in NORMAL_SCENARIOS.items():
        for attackers in ATTACKERS_VALUES:
            for pct in INTENSITIES_PCT:
                for rep in range(1, NUM_REPS + 1):
                    i += 1
                    if args.dry_run:
                        print(f"[DRY-RUN] [{i}/{total}] {scenario_name}_atk{pct}pct_att{attackers}_"
                              f"wu{atk_grid.WORK_UNITS}_rep{rep} (agg={agg})")
                        continue
                    print(f"\n[{i}/{total}]", flush=True)
                    atk_grid.run_point(scenario_name, agg, pct, attackers, rep)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}atacantes_intensidade_grid (S9-S11): "
          f"{total} execuções" + (" planejadas" if args.dry_run else " concluídas"))


if __name__ == "__main__":
    main()
