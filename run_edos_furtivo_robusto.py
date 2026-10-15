"""
Bateria ROBUSTA de furtividade (changes.txt §153). Consolida num único diretório
todo o espaço de parâmetros da furtividade, com protocolo uniforme (240 s, ataque
60-180 s), para a análise final. Modelo Sotelo Monge: WU_ataque > WU_normal.

Grid: RPS agregado {160,320} x WU_normal {10,100,1000,10000} x WU_ataque
{10000,20000,50000,100000,200000} x intensidade {1,5,10,15,20,25}% (228 células
de ataque, excluídas as 12 com WU_n=WU_a=10000) + 0% normal isolado por (RPS,WU_n).
1 repetição, com 10 s de pausa entre execuções (cooldown do Docker).

Reaproveitamento: as células já coletadas no protocolo 240 s (edos_furtivo_wu,
edos_furtivo_wu_rps) são copiadas para cá ANTES por copia_reaproveitaveis_robusto.py;
este runner PULA qualquer célula cujo metrics_ já exista -> resumível e sem repetir.

Uso: python3 run_edos_furtivo_robusto.py [--dry-run]
"""
import argparse
import os
import time

import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_robusto"
CLIENTES, ATACANTES = 4, 4
RPS_LIST = [160, 320]
WU_NORMAL = [10, 100, 1000, 10000]
WU_ATAQUE = [10000, 20000, 50000, 100000, 200000]
INTENS = [1, 5, 10, 15, 20, 25]
REPS = [1]
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 240, 60, 120  # ataque 60-180 s
COOLDOWN_S = 10
INCLUIR_BASELINE = True


def jobs_list():
    js = []
    for rep in REPS:
        for rps in RPS_LIST:
            for wn in WU_NORMAL:
                if INCLUIR_BASELINE:
                    js.append((rep, rps, wn, None, 0))
                for wa in WU_ATAQUE:
                    if wa <= wn:  # modelo: ataque mais pesado que o normal
                        continue
                    for pct in INTENS:
                        js.append((rep, rps, wn, wa, pct))
    return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    js = jobs_list()
    rodados = 0
    for i, (rep, rps, wn, wa, pct) in enumerate(js, 1):
        if pct == 0:
            suffix = f"agg{rps}_nwu{wn}_atk0pct_rep{rep}"
        else:
            suffix = f"agg{rps}_nwu{wn}_atk{pct}pct_awu{wa}_rep{rep}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv")):
            print(f"[JÁ EXISTE, pulando] [{i}/{len(js)}] {suffix}", flush=True)
            continue
        args = ["--normal-rps", str(rps / CLIENTES), "--normal-clients", str(CLIENTES),
                "--normal-work-units", str(wn), "--duration", str(DURACAO)]
        if pct == 0:
            args += ["--attack-duration", "0"]
        else:
            args += ["--rps", str(rps * pct / 100 / ATACANTES), "--attackers", str(ATACANTES),
                     "--work-units", str(wa),
                     "--attack-start", str(ATAQUE_INICIO), "--pulse-duration", str(ATAQUE_DURACAO)]
        if a.dry_run:
            print(f"[DRY-RUN] [{i}/{len(js)}] {suffix}: {' '.join(args)}")
            continue
        print(f"\n===== [{i}/{len(js)}] {suffix} =====", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
        rodados += 1
        time.sleep(COOLDOWN_S)  # deixa o Docker/host esfriar entre execuções
    print(f"concluído (rodadas nesta sessão: {rodados})", flush=True)


if __name__ == "__main__":
    main()
