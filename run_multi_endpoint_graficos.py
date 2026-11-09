"""
Baterias COMPLEMENTARES multi-endpoint p/ replicar os gráficos definitivos
(graficos_apresentacao/graficos_escolhidos.txt) sob o modelo de mistura de
endpoints. Três fontes de jobs, cada uma na sua pasta, todas em ISO2-B (780 s):

  D) ATAQUE ISOLADO (sem tráfego normal) -> replica o gráfico 27 (isolado × combinado).
     RPS_ref {160,240,320} × intensidade {1,5,10,15,20,25}% × 5 reps. Ataque só no
     maior endpoint (D=50000). Normal desligado (--normal-rps 0). (5 reps.)
     Pasta: experiment_results/multi_ataque_isolado/

  A) GRID CLIENTES × RPS (só normal) -> replica 11/17/20 (invariância por nº de
     clientes). Clientes {1,2,4,8,16} × RPS {160,240,320} × 3 reps, mistura.
     Pasta: experiment_results/multi_clientes_rps/

  B) VARREDURA RPS log2 (só normal) -> replica 42/60 (teto/capacidade ampla).
     RPS agregado {20,40,80,160,320,640,1280,2560} × 3 reps, 4 clientes, mistura.
     Pasta: experiment_results/multi_normal_log2/

Ordem de execução: D (ataque, mais valioso) -> A -> B. Resumível (pula metrics_
já existente). Cooldown 60 s entre runs. Uso: python3 run_multi_endpoint_graficos.py [--dry-run]
"""
import argparse
import os
import time

import docker_manager
import run_scaling_affected_rerun as base

ENDPOINTS = [(1000, 0.40), (5000, 0.30), (10000, 0.20), (50000, 0.10)]
ATAQUE_WU = max(c for c, _ in ENDPOINTS)
DIST_STR = ",".join(f"{c}:{p}" for c, p in ENDPOINTS)
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 780, 300, 300   # ISO2-B
COOLDOWN_S = 60
ATACANTES = 4

DIR_D = "experiment_results/multi_ataque_isolado"
DIR_A = "experiment_results/multi_clientes_rps"
DIR_B = "experiment_results/multi_normal_log2"

# D — ataque isolado
D_RPS_REF = [160, 240, 320]
D_INTENS = [1, 5, 10, 15, 20, 25]
D_REPS = [1, 2, 3, 4, 5]
# A — clientes × rps
A_CLIENTES = [1, 2, 4, 8, 16]
A_RPS = [160, 240, 320]
A_REPS = [1, 2, 3]
# B — varredura log2
B_RPS = [20, 40, 80, 160, 320, 640, 1280, 2560]
B_CLIENTES = 4
B_REPS = [1, 2, 3]


def jobs():
    js = []  # (dir, suffix, args, save_attack)
    # D: ataque isolado (sem normal)
    for rep in D_REPS:
        for rps in D_RPS_REF:
            for pct in D_INTENS:
                suf = f"agg{rps}_isolado_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"
                a = ["--normal-rps", "0",
                     "--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(ATAQUE_WU), "--attack-start", str(ATAQUE_INICIO),
                     "--pulse-duration", str(ATAQUE_DURACAO), "--duration", str(DURACAO)]
                js.append((DIR_D, suf, a, True))
    # A: clientes × rps (só normal)
    for rep in A_REPS:
        for clientes in A_CLIENTES:
            for rps in A_RPS:
                suf = f"agg{rps}_c{clientes}_mix_rep{rep}"
                a = ["--normal-rps", str(rps / clientes), "--normal-clients", str(clientes),
                     "--normal-work-dist", DIST_STR, "--duration", str(DURACAO), "--attack-duration", "0"]
                js.append((DIR_A, suf, a, False))
    # B: varredura log2 (só normal, 4 clientes)
    for rep in B_REPS:
        for rps in B_RPS:
            suf = f"agg{rps}_mix_rep{rep}"
            a = ["--normal-rps", str(rps / B_CLIENTES), "--normal-clients", str(B_CLIENTES),
                 "--normal-work-dist", DIST_STR, "--duration", str(DURACAO), "--attack-duration", "0"]
            js.append((DIR_B, suf, a, False))
    return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for d in (DIR_D, DIR_A, DIR_B):
        os.makedirs(d, exist_ok=True)
    js = jobs()
    feitos = sum(os.path.exists(os.path.join(d, f"metrics_{s}.csv")) for d, s, _, _ in js)
    print(f"Total de jobs: {len(js)} | já feitos: {feitos} | a rodar: {len(js) - feitos}", flush=True)
    rodados = 0
    for i, (d, suf, args, save_atk) in enumerate(js, 1):
        if os.path.exists(os.path.join(d, f"metrics_{suf}.csv")):
            print(f"[JA EXISTE, pulando] [{i}/{len(js)}] {suf}", flush=True)
            continue
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(js)}] {os.path.basename(d)}/{suf}: {' '.join(args)}", flush=True)
            continue
        print(f"\n===== [{i}/{len(js)}] {os.path.basename(d)}/{suf} =====", flush=True)
        try:
            docker_manager.cleanup_all_simulation_instances()
        except Exception as e:
            print(f"[AVISO] cleanup pre-run falhou: {e}", flush=True)
        base.run_and_collect(args, d, suf, save_attack_summary=save_atk, save_normal_summary=not save_atk)
        rodados += 1
        if i < len(js):
            time.sleep(COOLDOWN_S)
    print(f"\nbaterias de graficos concluidas (rodadas nesta sessao: {rodados})", flush=True)


if __name__ == "__main__":
    main()
