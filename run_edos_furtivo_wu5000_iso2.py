"""
Coluna WU_normal=5000 no protocolo ISO2 (changes.txt §158) — fecha o arco
1000 / 5000 / 10000 da bateria robusta ISO2.

Motivo: no grid robusto (WU_n 1000 e 10000) o regime furtivo-E-danoso não se
demonstra limpo — 1000 é leve demais (só escala quando já está barulhento no RTT),
10000 é pesada demais (escala até com 0% de ataque, logo a escalada não é causada
pelo ataque). WU_n=5000 (~40% CPU) fica no meio: NÃO escala sozinha, mas um ataque
de razão de custo baixa pode empurrá-la >60% sem mexer no RTT → furtivo ao detector
E causador da escalada ao mesmo tempo.

Escopo (aprovado pelo usuário): razões 2× (awu10000) e 4× (awu20000),
intensidade {10,15,20,25}% + baseline 0%, 3 reps. 9 células × 3 = 27 runs.

Mesmo timing/isolamento da bateria robusta ISO2 e MESMO diretório (dataset unificado).

Uso: python3 run_edos_furtivo_wu5000_iso2.py [--dry-run]
"""
import argparse
import os
import time

import docker_manager
import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_robusto_iso2"
CLIENTES, ATACANTES = 4, 4
RPS = 320
WU_NORMAL = [5000]
WU_ATAQUE = [10000, 20000]  # razão 2× e 4× vs WU_normal=5000
INTENS = [10, 15, 20, 25]
REPS = [1, 2, 3]

DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 630, 300, 150  # ISO2
COOLDOWN_S = 60
INCLUIR_BASELINE = True


def jobs_list():
    js = []
    for rep in REPS:
        for wn in WU_NORMAL:
            if INCLUIR_BASELINE:
                js.append((rep, wn, None, 0))
            for wa in WU_ATAQUE:
                if wa <= wn:
                    continue
                for pct in INTENS:
                    js.append((rep, wn, wa, pct))
    return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    js = jobs_list()
    rodados = 0
    for i, (rep, wn, wa, pct) in enumerate(js, 1):
        if pct == 0:
            suffix = f"agg{RPS}_nwu{wn}_atk0pct_rep{rep}"
        else:
            suffix = f"agg{RPS}_nwu{wn}_atk{pct}pct_awu{wa}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print(f"[JA EXISTE, pulando] [{i}/{len(js)}] {suffix}", flush=True)
            continue
        args = ["--normal-rps", str(RPS / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(wn), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(RPS * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(wa),
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
        time.sleep(COOLDOWN_S)
    print(f"\niso2 wu5000 concluido (rodadas nesta sessao: {rodados})", flush=True)


if __name__ == "__main__":
    main()
