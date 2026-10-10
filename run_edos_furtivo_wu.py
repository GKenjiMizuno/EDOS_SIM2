"""
EDoS furtivo variando a WU do tráfego normal (changes.txt §144, pedido do
orientador). Hipótese: subindo a WU do normal, o RTT do ataque fica parecido
com o do tráfego normal e o ataque pode ficar furtivo ao detector de RTT.

Fixo: 320 rps de tráfego normal (4 clientes x 80 rps), ataque WU=200.000
(4 atacantes). Varia: WU do normal em {10, 100, 1000, 10000} x intensidade do
ataque em {0, 1, 5, 10, 15, 20, 25}% (0% = tráfego normal ISOLADO, para
comparação). 1 repetição (exploração).

Tempo espaçado (Opção B, sem mudar o autoscaler): duração 240 s, ataque de 60 a
180 s (--attack-start 60 --pulse-duration 120), 60 s de pré-ataque para a
baseline estabilizar depois do pico de arranque e 60 s de pós-ataque para os
detectores/instâncias esfriarem.

Uso: python3 run_edos_furtivo_wu.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_wu"
NORMAL_RPS_AGG, CLIENTES = 320, 4
ATK_WU, ATACANTES = 200000, 4
WU_NORMAL = [10, 100, 1000, 10000]
INTENSIDADES = [0, 1, 5, 10, 15, 20, 25]
REPS = [1]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120  # ataque 60-180 s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, wu, pct) for rep in REPS for wu in WU_NORMAL for pct in INTENSIDADES]
    for i, (rep, wu, pct) in enumerate(jobs, 1):
        suffix = f"agg{NORMAL_RPS_AGG}_nwu{wu}_atk{pct}pct_awu{ATK_WU}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(NORMAL_RPS_AGG / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(wu), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(NORMAL_RPS_AGG * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(ATK_WU),
                     "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}] {suffix}: {' '.join(args)}")
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
