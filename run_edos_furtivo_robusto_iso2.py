"""
Bateria ROBUSTA de furtividade — RE-COLETA com timing ISO2 (changes.txt §157).

Motivação: o protocolo de 240 s usava baseline [15,60), curto o bastante para ser
contaminado pelo pico de arranque / escalonamento tardio perto do limiar de 60 % CPU,
gerando furtividade FALSA (bimodalidade entre reps, ver 5× isolado vs ISO2 na conversa
de 2026-10-23). O timing ISO2 — 5 min só normal, 2 min 30 s de ataque, 3 min final —
dá um baseline longo e estável [60,300) e foi o que eliminou o artefato. Esta bateria
re-roda a SELEÇÃO relevante do grid robusto (não o grid inteiro) com esse timing e
3 repetições por célula, para a análise final da tese.

Seleção (só valores que já estavam no grid robusto — não invento parâmetros novos):
  RPS agregado: 320 (vítima documentada)
  WU_normal: {1000, 10000}   (exclui 10/100: σ minúsculo → CUSUM pega tudo, artefato)
  WU_ataque: {10000,20000,50000,100000,200000}, restrição WU_ataque > WU_normal
  intensidade: {1,5,10,15,20,25} %
  + baseline 0 % por WU_normal
  3 repetições por célula.

Contagem: WU_n=1000 → 5×6+1 = 31 ; WU_n=10000 → 4×6+1 = 25 ; = 56 células × 3 = 168 runs.

Isolamento: limpa todos os containers da simulação ANTES de cada run (resquício zero)
e 60 s de pausa entre runs (Docker descansar). Resumível: pula célula cujo metrics_ já
exista. Grava em diretório próprio para não colidir com os dados de 240 s.

Uso: python3 run_edos_furtivo_robusto_iso2.py [--dry-run]
"""
import argparse
import os
import time

import docker_manager
import run_scaling_affected_rerun as base

RESULTS_DIR = "experiment_results/edos_furtivo_robusto_iso2"
CLIENTES, ATACANTES = 4, 4
RPS = 320
WU_NORMAL = [1000, 10000]
WU_ATAQUE = [10000, 20000, 50000, 100000, 200000]
INTENS = [1, 5, 10, 15, 20, 25]
REPS = [1, 2, 3]

# Timing ISO2: 0-300 s só normal (baseline estável), 300-450 s ataque (2 min 30 s),
# 450-630 s final (3 min). Janela de baseline dos detectores = [60,300) na análise.
DURACAO, ATAQUE_INICIO, ATAQUE_DURACAO = 630, 300, 150
COOLDOWN_S = 60  # pausa entre runs para o Docker/host esfriar
INCLUIR_BASELINE = True


def jobs_list():
    js = []
    for rep in REPS:
        for wn in WU_NORMAL:
            if INCLUIR_BASELINE:
                js.append((rep, wn, None, 0))
            for wa in WU_ATAQUE:
                if wa <= wn:  # modelo Sotelo Monge: ataque mais pesado que o normal
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
        # Resquicio zero: limpa qualquer container da simulacao antes de comecar.
        try:
            docker_manager.cleanup_all_simulation_instances()
        except Exception as e:
            print(f"[AVISO] cleanup pre-run falhou: {e}", flush=True)
        base.run_and_collect(args, RESULTS_DIR, suffix, save_attack_summary=pct > 0, save_normal_summary=True)
        rodados += 1
        time.sleep(COOLDOWN_S)
    print(f"\niso2 robusto concluido (rodadas nesta sessao: {rodados})", flush=True)


if __name__ == "__main__":
    main()
