"""
Confirmação das células furtivas (changes.txt §151): as 4 células que no §149/§150
escalaram com combinado 0/11 (1 rep). Roda reps 2-5 (a rep1 já existe) para ter
5 repetições independentes e medir em quantas o ataque fica furtivo-e-escalando.

Fixo: 320 rps agregado, WU_normal=5000 (igual §149). Células:
  (WU_ataque, intensidade): (10000,15) (10000,20) (10000,30) (20000,15)
Reps 2-5. Tempo espaçado: 240 s, ataque 60-180 s.
Escreve na MESMA pasta experiment_results/edos_furtivo_wu_baixo/.

Uso: python3 run_edos_furtivo_confirma.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_wu_baixo"
RPS_AGG, CLIENTES, ATACANTES = 320, 4, 4
WU_NORMAL = 5000
CELULAS = [(10000, 15), (10000, 20), (10000, 30), (20000, 15)]
REPS = [2, 3, 4, 5]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, wu_a, pct) for rep in REPS for (wu_a, pct) in CELULAS]
    for i, (rep, wu_a, pct) in enumerate(jobs, 1):
        suffix = f"agg{RPS_AGG}_nwu{WU_NORMAL}_atk{pct}pct_awu{wu_a}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(RPS_AGG / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(WU_NORMAL), "--duration", str(DURACAO),
                "--rps", str(RPS_AGG * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                "--work-units", str(wu_a),
                "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}] {suffix}: {' '.join(args)}")
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=True, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
