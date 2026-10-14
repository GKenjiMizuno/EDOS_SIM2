"""
EDoS furtivo com WU do ataque MÍNIMO (changes.txt §149): mapeia a fronteira de
furtividade com o menor contraste de RTT possível. Na bateria 3D (§147/§148) as
células quase-furtivas apareceram em 320 rps, WU_normal=5000, WU_ataque baixo.
Aqui descemos o WU_ataque ainda mais (perto do normal) e subimos a intensidade
(requisição mais leve precisa de mais volume para escalar).

Fixo: 320 rps agregado (--normal-rps 80 --normal-clients 4), WU_normal=5000.
Ataque: 4 atacantes. Varia: WU_ataque {10000,20000,30000,40000} (razão 2-8x,
sempre > WU_normal) x intensidade {5,10,15,20,30}% (+ 0% normal isolado).
1 repetição. Tempo espaçado: 240 s, ataque 60-180 s.

Uso: python3 run_edos_furtivo_baixo.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_wu_baixo"
RPS_AGG, CLIENTES, ATACANTES = 320, 4, 4
WU_NORMAL = 5000
WU_ATAQUE = [10000, 20000, 30000, 40000]
INTENSIDADES = [0, 5, 10, 15, 20, 30]
REPS = [1]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120  # ataque 60-180 s


def jobs_list():
    jobs = []
    for rep in REPS:
        jobs.append((rep, None, 0))  # normal isolado
        for wu_a in WU_ATAQUE:
            for pct in INTENSIDADES:
                if pct == 0:
                    continue
                jobs.append((rep, wu_a, pct))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = jobs_list()
    for i, (rep, wu_a, pct) in enumerate(jobs, 1):
        if pct == 0:
            suffix = f"agg{RPS_AGG}_nwu{WU_NORMAL}_atk0pct_rep{rep}"
        else:
            suffix = f"agg{RPS_AGG}_nwu{WU_NORMAL}_atk{pct}pct_awu{wu_a}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(RPS_AGG / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(WU_NORMAL), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(RPS_AGG * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(wu_a),
                     "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}] {suffix}: {' '.join(args)}")
            continue
        print(f"\n===== [{i}/{len(jobs)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
