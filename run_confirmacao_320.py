"""
Confirmação do achado do §120 (changes.txt §121): base normal WU=10000 a 320
rps agregado (4 clientes x 80), ataque WU=200000 com 4 atacantes a 0%
(controle, sem ataque), 1% e 5%; simulação completa de 180 s, ataque em
[20,160] s (defaults do config); 3 repetições. Captura desligada.

Uso: python3 run_confirmacao_320.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

NORMAL_AGG, NORMAL_WU, CLIENTES = 320, 10000, 4
ATK_WU, ATACANTES = 200000, 4
INTENSIDADES = [0, 1, 5]
REPS = [1, 2, 3]
RESULTS_DIR = "experiment_results/confirmacao_320"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, pct) for rep in REPS for pct in INTENSIDADES]  # intercala condições por repetição
    for i, (rep, pct) in enumerate(jobs, 1):
        suffix = f"agg{NORMAL_AGG}_nwu{NORMAL_WU}_atk{pct}pct_awu{ATK_WU}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(NORMAL_AGG / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(NORMAL_WU), "--duration", "180"]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(NORMAL_AGG * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(ATK_WU)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}]", suffix, args)
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
