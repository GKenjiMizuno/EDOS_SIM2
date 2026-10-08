"""
Teste simples (pedido do usuário, changes.txt §118): tráfego normal ISOLADO
com WU por requisição = 100, 1000 e 10000 x agregado 20-640 rps, 1 repetição,
4 clientes, 60 s por execução. Objetivo: ver como o "endpoint
normal" se comporta (CPU, RTT, ruído do RTT, escalonamento) conforme o custo
por requisição sobe, antes de definir o par endpoint normal x endpoint de
ataque. Referência WU=10 nessa mesma carga já existe em normal_baseline/.

Diretório próprio: experiment_results/normal_wu_teste/ (não mistura com
nenhuma família existente). Captura de pacotes continua desligada.

Uso: python3 run_normal_wu_teste.py [--dry-run]
"""
import argparse
import os

import run_scaling_affected_rerun as base

WUS = [100, 1000, 10000]
AGGS = [20, 40, 80, 160, 320, 640]  # mesmos agregados de normal_isolado_pos_lb
CLIENTES = 4
DURACAO = 60  # teste rápido (pedido do usuário), não a simulação de 180 s
RESULTS_DIR = "experiment_results/normal_wu_teste"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    jobs = [(wu, agg) for wu in WUS for agg in AGGS]
    for i, (wu, agg) in enumerate(jobs, 1):
        suffix = f"agg{agg}_WU{wu}_rep1"
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(jobs)}] {suffix}")
            continue
        print(f"\n===== [{i}/{len(jobs)}] normal isolado {suffix} =====", flush=True)
        base.run_and_collect(
            ["--normal-rps", str(agg / CLIENTES), "--normal-clients", str(CLIENTES),
             "--normal-work-units", str(wu), "--attack-duration", "0", "--duration", str(DURACAO)],
            RESULTS_DIR, suffix, save_attack_summary=False, save_normal_summary=True)
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
