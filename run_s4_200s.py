"""
Reexecução dos testes dos gráficos 65/66 com 200 s (changes.txt §130):
o ataque continua em 20-160 s, sobram 40 s depois do ataque para ver se os
detectores voltam a "normal".
  - combinado: S4, normal 300 rps (4 clientes x 75, WU=10) + ataque 10% =
    30 rps (4 atacantes x 7,5, WU=400.000) -- mesmos parâmetros do
    wedos_grid S4_atk10pct_wu400000;
  - normal isolado: S4, 300 rps (4 x 75, WU=10), sem ataque.
5 repetições de cada, intercaladas. Captura do tcpdump fica como está hoje
(sem cap_net_raw -> vazia), igual aos dados originais.

Uso: python3 run_s4_200s.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/s4_200s"
REPS = [1]  # usuário pediu só 1 repetição
COMUM = ["--normal-rps", "75", "--normal-clients", "4", "--normal-work-units", "10", "--duration", "200"]
CASOS = {
    "S4_atk10pct_wu400000_200s": COMUM + ["--rps", "7.5", "--attackers", "4", "--work-units", "400000"],
    "normal_agg300_WU10_200s": COMUM + ["--attack-duration", "0"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, nome) for rep in REPS for nome in CASOS]
    for i, (rep, nome) in enumerate(jobs, 1):
        suffix = f"{nome}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}]", suffix, CASOS[nome])
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(CASOS[nome], RESULTS_DIR, suffix,
                             save_attack_summary=nome.startswith("S4_atk"), save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
