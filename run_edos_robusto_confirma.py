"""
Confirmação das 3 células furtivas da bateria robusta (changes.txt §155, §154).
Roda reps 2-5 (rep1 já existe em edos_furtivo_robusto/). Células furtivas-e-
escalaram (combinado 0/11) a confirmar:
  (RPS, WU_normal, WU_ataque, intensidade):
  (160, 10000, 20000, 25) ; (320, 1000, 20000, 20) ; (320, 10000, 50000, 15)
Protocolo: 240 s, ataque 60-180 s, 4 clientes/atacantes, 10 s de cooldown.
Escreve na MESMA pasta experiment_results/edos_furtivo_robusto/.

Uso: python3 run_edos_robusto_confirma.py [--dry-run]
"""
import argparse
import os
import time

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_robusto"
CLIENTES, ATACANTES = 4, 4
# (rps, wu_normal, wu_ataque, intensidade)
CELULAS = [(160, 10000, 20000, 25), (320, 1000, 20000, 20), (320, 10000, 50000, 15)]
REPS = [2, 3, 4, 5]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120
COOLDOWN_S = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, rps, wn, wa, pct) for rep in REPS for (rps, wn, wa, pct) in CELULAS]
    for i, (rep, rps, wn, wa, pct) in enumerate(jobs, 1):
        suffix = f"agg{rps}_nwu{wn}_atk{pct}pct_awu{wa}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(rps / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(wn), "--duration", str(DURACAO),
                "--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                "--work-units", str(wa),
                "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}] {suffix}: {' '.join(args)}")
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=True, save_normal_summary=True)
        time.sleep(COOLDOWN_S)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
