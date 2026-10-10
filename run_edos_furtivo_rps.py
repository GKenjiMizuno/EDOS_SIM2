"""
EDoS furtivo variando o RPS do tráfego normal entre 160 e 320 (changes.txt §146).
Continuação da bateria §144: lá variamos a WU do normal com RPS fixo em 320; aqui
fixamos a WU do normal em 10.000 (endpoint leve do cliente) e variamos o RPS do
normal em {160, 240, 320}, mantendo o ataque baixo-RPS/alto-WU (WU=200.000,
endpoint pesado do atacante -- modelo de Sotelo Monge: WU_ataque > WU_normal).

Hipótese: a furtividade ao detector de RTT vem da DILUIÇÃO (as poucas requisições
pesadas do ataque não movem a estatística da janela se forem fração < ~1,9% do
total -- limiar do Z robusto). Varre intensidades baixas para mapear a fronteira
"escala mas fica furtivo".

Fixo: WU normal=10.000, 4 clientes; ataque WU=200.000, 4 atacantes. 1 repetição.
Tempo espaçado (Opção B): duração 240 s, ataque 60-180 s.

Uso: python3 run_edos_furtivo_rps.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_rps"
CLIENTES = 4
WU_NORMAL = 10000
ATK_WU, ATACANTES = 200000, 4
RPS_NORMAL = [160, 240, 320]
INTENSIDADES = [0, 1, 2, 3, 5, 10]
REPS = [1]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120  # ataque 60-180 s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(rep, rps, pct) for rep in REPS for rps in RPS_NORMAL for pct in INTENSIDADES]
    for i, (rep, rps, pct) in enumerate(jobs, 1):
        suffix = f"agg{rps}_nwu{WU_NORMAL}_atk{pct}pct_awu{ATK_WU}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print("[JÁ EXISTE, pulando]", suffix)
            continue
        args = ["--normal-rps", str(rps / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(WU_NORMAL), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
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
