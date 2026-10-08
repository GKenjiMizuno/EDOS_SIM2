"""
Teste rápido (changes.txt §119): 2 "endpoints" -- normal WU=10000 a 160 rps
agregado (4 clientes x 40) e ataque WU=200000 com 4 atacantes, intensidade
1/5/10% do agregado normal. 1 repetição, 60 s, ataque em [20, 60] s
(--pulse-duration 40). Captura de pacotes desligada.
Controle sem ataque: experiment_results/normal_wu_teste/*agg160_WU10000_rep1*.

Uso: python3 run_ataque_wu_teste.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

NORMAL_WU, CLIENTES = 10000, 4
ATK_WU, ATACANTES = 200000, 4
# (agregado normal, intensidade %). §119: 160 rps x 1/5/10. §120: opção B (320
# rps, mais perto do limiar) x 1-25%, e 160 rps completado com 15/20/25%.
# Execuções que já existem em disco são puladas (não refaz nem sobrescreve).
JOBS = [(160, p) for p in (1, 5, 10, 15, 20, 25)] + [(320, p) for p in (1, 5, 10, 15, 20, 25)]
RESULTS_DIR = "experiment_results/ataque_wu_teste"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for NORMAL_AGG, pct in JOBS:
        atk_rps = NORMAL_AGG * pct / 100 / ATACANTES
        suffix = f"agg{NORMAL_AGG}_nwu{NORMAL_WU}_atk{pct}pct_awu{ATK_WU}_rep1"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(NORMAL_AGG / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(NORMAL_WU),
                "--rps", str(atk_rps), "--attackers", str(ATACANTES), "--work-units", str(ATK_WU),
                "--attack-start", "20", "--pulse-duration", "40", "--duration", "60"]
        if a.dry_run:
            print("[DRY-RUN]", suffix, args)
            continue
        print(f"\n===== {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=True, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
