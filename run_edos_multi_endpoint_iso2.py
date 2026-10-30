"""
Bateria multi-endpoint (modelo Sotelo Monge 2017 / EDiSON) com timing ISO2.

Trafego normal = MISTURA de endpoints de custos diferentes, sorteados por peso em
cada requisicao (--normal-work-dist). Ataque concentrado SO no maior endpoint do
menu (carga = max das cargas), variando a intensidade. Mesmo comportamento do
simulador, so o trafego normal muda.

Numero e cargas dos endpoints sao livres: basta editar ENDPOINTS abaixo. Com o
menu padrao {1000:.4, 5000:.3, 10000:.2, 50000:.1}, o WU_n efetivo (media
ponderada) ~ 8900 e o ataque usa 50000 (== endpoint legitimo mais pesado).

Para voltar ao simulador "de carga unica", basta NAO usar esta bateria (o modo
single e o padrao do config/CLI) -- nada aqui altera o comportamento default.

Grade: RPS agregado {160,320} x intensidade {1,5,10,15,20,25}% + baseline 0%,
3 reps. = 2 x 7 x 3 = 42 runs. Timing ISO2-B (ataque alongado p/ equilibrio de
classe no ML): 0-300 so normal (baseline [60,300)), 300-600 ataque (5 min),
600-780 final (3 min). Cooldown 60s entre runs (Docker esfriar). Resumivel.

Uso: python3 run_edos_multi_endpoint_iso2.py [--dry-run]
"""
import argparse
import os
import time

import docker_manager
import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_multi_endpoint_iso2"
CLIENTES, ATACANTES = 4, 4
RPS_LIST = [160, 240, 320]
# Menu de endpoints (carga, peso). Numero e cargas livres -- editar aqui.
ENDPOINTS = [(1000, 0.40), (5000, 0.30), (10000, 0.20), (50000, 0.10)]
INTENS = [1, 5, 10, 15, 20, 25]
REPS = [1, 2, 3]

DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 780, 300, 300  # ISO2-B: baseline 300 / ataque 300 / final 180
COOLDOWN_S = 60
INCLUIR_BASELINE = True

ATAQUE_WU = max(c for c, _ in ENDPOINTS)   # ataque so no maior endpoint
DIST_STR = ",".join(f"{c}:{p}" for c, p in ENDPOINTS)


def jobs_list():
    js = []
    for rep in REPS:
        for rps in RPS_LIST:
            if INCLUIR_BASELINE:
                js.append((rep, rps, 0))
            for pct in INTENS:
                js.append((rep, rps, pct))
    return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    js = jobs_list()
    rodados = 0
    for i, (rep, rps, pct) in enumerate(js, 1):
        if pct == 0:
            suffix = f"agg{rps}_mix_atk0pct_rep{rep}"
        else:
            suffix = f"agg{rps}_mix_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print(f"[JA EXISTE, pulando] [{i}/{len(js)}] {suffix}", flush=True)
            continue
        args = ["--normal-rps", str(rps / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-dist", DIST_STR, "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(ATAQUE_WU),
                     "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(js)}] {suffix}: {' '.join(args)}", flush=True)
            continue
        print(f"\n===== [{i}/{len(js)}] {suffix} =====", flush=True)
        try:
            docker_manager.cleanup_all_simulation_instances()
        except Exception as e:
            print(f"[AVISO] cleanup pre-run falhou: {e}", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
        rodados += 1
        if i < len(js):
            time.sleep(COOLDOWN_S)
    print(f"\nmulti-endpoint iso2 concluido (rodadas nesta sessao: {rodados})", flush=True)


if __name__ == "__main__":
    main()
