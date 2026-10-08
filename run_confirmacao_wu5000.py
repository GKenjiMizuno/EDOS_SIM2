"""
Bateria de confirmação com endpoint normal mais barato (changes.txt §122):
base normal WU=5000 a 160 e 320 rps agregado (4 clientes), ataque WU=200000
com 4 atacantes a 0% (controle), 1%, 5% e 10%; 180 s, ataque [20,160] s;
3 repetições intercaladas. Captura desligada. Motivo: a 320 rps com WU=10000
o tráfego normal sozinho escalava (§121); WU=5000 deixa as duas bases abaixo
do limiar (~20% e ~35-40% de CPU estimados).

Uso: python3 run_confirmacao_wu5000.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

NORMAL_WU, CLIENTES = 5000, 4
ATK_WU, ATACANTES = 200000, 4
CARGAS = [160, 320]
INTENSIDADES = [0, 1, 5, 10]
REPS = [1, 2, 3]
RESULTS_DIR = "experiment_results/confirmacao_wu5000"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, agg, pct) for rep in REPS for agg in CARGAS for pct in INTENSIDADES]
    for i, (rep, agg, pct) in enumerate(jobs, 1):
        suffix = f"agg{agg}_nwu{NORMAL_WU}_atk{pct}pct_awu{ATK_WU}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(agg / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(NORMAL_WU), "--duration", "180"]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(agg * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(ATK_WU)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}]", suffix)
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
