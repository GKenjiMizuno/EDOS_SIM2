"""
Bateria DEFINITIVA multi-endpoint (modelo Sotelo Monge / EDiSON), 5 repetições.
Mesma física do simulador; só o tráfego normal é a MISTURA de endpoints por peso.

Duas fontes de jobs (todas em timing ISO2-B, 780 s, p/ consistência):
  A) VARREDURA DE BASELINE (só tráfego normal, sem ataque) — caracteriza a curva de
     capacidade/escalonamento da mistura e justifica o RPS central (240):
        RPS agregado {120,160,200,240,280,320} × 5 reps.
  B) GRID DE ATAQUE (normal + ataque só no maior endpoint, D=50000):
        RPS {160,240,320} × intensidade {1,5,10,15,20,25}% × 5 reps.

Reaproveita os runs já feitos (3 reps de A@{160,240,320} e de B): resume-skip por
metrics_ existente — só roda o que falta (reps 4-5 e os RPS novos de baseline).
Cooldown de 60 s entre runs (Docker esfriar). Mesma pasta da bateria exploratória.

Uso: python3 run_multi_endpoint_definitivo.py [--dry-run]
"""
import argparse
import os
import time

import docker_manager
import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_multi_endpoint_iso2"
CLIENTES, ATACANTES = 4, 4
ENDPOINTS = [(1000, 0.40), (5000, 0.30), (10000, 0.20), (50000, 0.10)]
REPS = [1, 2, 3, 4, 5]                       # 5 reps (robustez)

RPS_BASELINE = [120, 160, 200, 240, 280, 320]   # varredura A (só normal)
RPS_ATAQUE = [160, 240, 320]                     # grid B (normal + ataque)
INTENS = [1, 5, 10, 15, 20, 25]

DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 780, 300, 300   # ISO2-B
COOLDOWN_S = 60
ATAQUE_WU = max(c for c, _ in ENDPOINTS)     # ataque só no endpoint de maior demanda
DIST_STR = ",".join(f"{c}:{p}" for c, p in ENDPOINTS)


def jobs_list():
    """(rep, rps, pct). pct=0 => baseline. rep é o laço externo p/ reps completas cedo."""
    js = []
    for rep in REPS:
        for rps in RPS_BASELINE:                 # A: baselines (inclui 160/240/320)
            js.append((rep, rps, 0))
        for rps in RPS_ATAQUE:                   # B: ataque
            for pct in INTENS:
                js.append((rep, rps, pct))
    return js


def suffix_de(rps, pct, rep):
    if pct == 0:
        return f"agg{rps}_mix_atk0pct_rep{rep}"
    return f"agg{rps}_mix_atk{pct}pct_awu{ATAQUE_WU}_rep{rep}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    js = jobs_list()
    pendentes = [(rep, rps, pct) for (rep, rps, pct) in js
                 if not os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix_de(rps, pct, rep)}.csv"))]
    print(f"Total de jobs: {len(js)} | já feitos: {len(js) - len(pendentes)} | a rodar: {len(pendentes)}", flush=True)
    rodados = 0
    for i, (rep, rps, pct) in enumerate(js, 1):
        suffix = suffix_de(rps, pct, rep)
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
    print(f"\nbateria definitiva multi-endpoint concluida (rodadas nesta sessao: {rodados})", flush=True)


if __name__ == "__main__":
    main()
