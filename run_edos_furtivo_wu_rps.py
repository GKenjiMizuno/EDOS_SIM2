"""
EDoS furtivo 3D: RPS x WU_normal x WU_ataque x intensidade (changes.txt §147).
Pedido do usuário após §144-146. Modelo de Sotelo Monge: endpoint leve do cliente
(WU_normal) e endpoint pesado do atacante (WU_ataque), com WU_ataque > WU_normal.

Varre:
  RPS agregado do normal: {160, 320}  (--normal-rps = rps/4, --normal-clients 4)
  WU do normal (leve):    {5000, 10000}
  WU do ataque (pesado):  {50000, 100000, 200000}   (sempre > WU_normal)
  intensidade do ataque:  {1, 5, 10}%   (+ 0% = normal isolado, 1x por RPS/WU_normal)
4 atacantes, 4 clientes, 1 repetição. Tempo espaçado: 240 s, ataque 60-180 s.

Objetivo: mapear onde o ataque ESCALA mas fica FURTIVO ao detector de RTT (via
diluição: fração do ataque < ~1,9% do total; e contraste de RTT reduzido quando
WU_normal sobe e/ou WU_ataque desce).

Uso: python3 run_edos_furtivo_wu_rps.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_wu_rps"
CLIENTES, ATACANTES = 4, 4
RPS_NORMAL = [160, 320]
WU_NORMAL = [5000, 10000]
WU_ATAQUE = [50000, 100000, 200000]
INTENSIDADES = [1, 5, 10]
REPS = [1]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120  # ataque 60-180 s


def jobs_list():
    jobs = []
    for rep in REPS:
        for rps in RPS_NORMAL:
            for wu_n in WU_NORMAL:
                # normal isolado (0%): 1x por (rps, wu_n), independe do WU do ataque
                jobs.append((rep, rps, wu_n, None, 0))
                for wu_a in WU_ATAQUE:
                    if wu_a <= wu_n:
                        continue  # modelo: ataque tem que ser mais pesado que o normal
                    for pct in INTENSIDADES:
                        jobs.append((rep, rps, wu_n, wu_a, pct))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = jobs_list()
    for i, (rep, rps, wu_n, wu_a, pct) in enumerate(jobs, 1):
        if pct == 0:
            suffix = f"agg{rps}_nwu{wu_n}_atk0pct_rep{rep}"
        else:
            suffix = f"agg{rps}_nwu{wu_n}_atk{pct}pct_awu{wu_a}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(rps / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(wu_n), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
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
