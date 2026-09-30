"""
Recoleta dos runs afetados pelo bug do normal_traffic.py corrigido pelo
load_balancer.py (ver changes.txt §102-103): qualquer run que teve pelo
menos 1 SCALE_UP tinha a instância nova recebendo tráfego normal zero (ou,
no caso do ataque, sofria um buraco de ~1s a cada reinício). Este script
identifica esses runs (por decision=='SCALE_UP' em algum tick do
metrics_*.csv real) e os recoleta com o código corrigido, preservando os
parâmetros originais de cada um -- reaproveitando as mesmas funções/fórmulas
dos scripts que geraram os dados originalmente, não reconstruindo do zero.

Caso especial: combined_sweep é expandido de 1 repetição (N=1, sem sufixo
_repN no nome) para 5 repetições completas (todas as 24 configs, afetadas
ou não), pra ficar consistente com o resto do dataset -- decisão explícita
do usuário, não um efeito colateral da correção do bug.

Todo arquivo antigo é copiado para experiment_results/_pre_loadbalancer_fix/
antes de ser sobrescrito -- nada é descartado.

Uso:
  python3 run_scaling_affected_rerun.py --dry-run   # só lista os comandos, não roda nada
  python3 run_scaling_affected_rerun.py              # roda de verdade
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import pandas as pd

import wedos_combined_grid as wg
import run_atacantes_intensidade_grid as atk_grid

BACKUP_ROOT = "experiment_results/_pre_loadbalancer_fix"

ALL_PREFIXES = ["metrics_", "rtt_log_", "traffic_capture_",
                "attack_summary_log_", "normal_traffic_summary_log_"]


def backup_existing(dir_path, suffix):
    """Move qualquer arquivo antigo com esse sufixo para o backup, sem apagar nada."""
    backup_dir = os.path.join(BACKUP_ROOT, os.path.basename(dir_path))
    moved = []
    for prefix in ALL_PREFIXES:
        src = os.path.join(dir_path, f"{prefix}{suffix}.csv")
        if os.path.exists(src):
            os.makedirs(backup_dir, exist_ok=True)
            shutil.move(src, os.path.join(backup_dir, f"{prefix}{suffix}.csv"))
            moved.append(src)
    return moved


def run_and_collect(cmd_args, dir_path, suffix, save_attack_summary=True,
                     save_normal_summary=True):
    """Roda main_orchestrator.py e move os arquivos de saída pra dir_path/prefix+suffix.csv."""
    cmd = ["python3", "main_orchestrator.py"] + cmd_args
    subprocess.run(cmd)

    def move_if_exists(src_name, prefix):
        if os.path.exists(src_name):
            shutil.move(src_name, os.path.join(dir_path, f"{prefix}{suffix}.csv"))

    move_if_exists("simulation_metrics.csv", "metrics_")
    move_if_exists("rtt_log.csv", "rtt_log_")
    move_if_exists("traffic_capture.csv", "traffic_capture_")

    if save_attack_summary:
        move_if_exists("attack_summary_log.csv", "attack_summary_log_")
    elif os.path.exists("attack_summary_log.csv"):
        os.remove("attack_summary_log.csv")

    if save_normal_summary:
        move_if_exists("normal_traffic_summary_log.csv", "normal_traffic_summary_log_")
    elif os.path.exists("normal_traffic_summary_log.csv"):
        os.remove("normal_traffic_summary_log.csv")


def find_affected(dir_path):
    affected = []
    for f in sorted(glob.glob(os.path.join(dir_path, "metrics_*.csv"))):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if (df["decision"] == "SCALE_UP").any():
            suffix = os.path.basename(f)[len("metrics_"):-len(".csv")]
            affected.append(suffix)
    return affected


# ---------------------------------------------------------------------------
# wedos_grid -- reaproveita wedos_combined_grid.run_point() direto, mesma
# fórmula/tag/nome de arquivo do original (a única mudança é o código
# corrigido do load balancer por baixo).
# ---------------------------------------------------------------------------
WEDOS_RE = re.compile(r"^(S\d+)_atk([\d.]+)pct_wu(\d+)_(.+)_rep(\d+)$")


def jobs_wedos_grid(dry_run):
    dir_path = "experiment_results/wedos_grid"
    jobs = []
    for suffix in find_affected(dir_path):
        m = WEDOS_RE.match(suffix)
        if not m:
            print(f"[AVISO] wedos_grid: sufixo fora do padrão, pulando: {suffix}")
            continue
        scenario, pct_s, wu_s, tag, rep_s = m.groups()
        pct = float(pct_s) if "." in pct_s else int(pct_s)
        jobs.append((scenario, wg.NORMAL_SCENARIOS[scenario], pct, int(wu_s), int(rep_s), tag))
    for scenario, agg, pct, wu, rep, tag in jobs:
        suffix = f"{scenario}_atk{pct}pct_wu{wu}_{tag}_rep{rep}"
        if dry_run:
            print(f"[DRY-RUN] wedos_grid: {suffix}")
            continue
        backup_existing(dir_path, suffix)
        wg.run_point(scenario, agg, pct, wu, rep=rep, tag=tag)
    return len(jobs)


# ---------------------------------------------------------------------------
# combined_sweep -- EXPANDE de 1 rep (sem sufixo) pra 5 reps completas, todas
# as 24 configs (não só as afetadas). Fórmula idêntica a
# run_experiments_combined.py, com normal_traffic_summary_log agora também
# salvo (o script original não salvava -- é anterior à correção §35 --
# aproveitando que já estamos regenerando tudo, ver changes.txt).
# ---------------------------------------------------------------------------
COMBINED_NORMAL_SCENARIOS = {"S1": 40, "S2": 100, "S3": 200, "S4": 300}
COMBINED_INTENSITIES_PCT = [1, 5, 10]
COMBINED_WORK_UNITS_LIST = [300000, 500000]
COMBINED_NUM_REPS = 5
COMBINED_NORMAL_NUM_CLIENTS = 4
COMBINED_ATTACK_NUM_ATTACKERS = 4
COMBINED_NORMAL_WORK_UNITS = 10


def jobs_combined_sweep(dry_run):
    dir_path = "experiment_results/combined_sweep"
    n = 0
    for scenario, agg in COMBINED_NORMAL_SCENARIOS.items():
        for pct in COMBINED_INTENSITIES_PCT:
            for wu in COMBINED_WORK_UNITS_LIST:
                for rep in range(1, COMBINED_NUM_REPS + 1):
                    n += 1
                    suffix = f"{scenario}_atk{pct}pct_wu{wu}_rep{rep}"
                    if dry_run:
                        print(f"[DRY-RUN] combined_sweep: {suffix}")
                        continue
                    attack_aggregate_rps = agg * pct / 100.0
                    normal_rps_per_client = agg / COMBINED_NORMAL_NUM_CLIENTS
                    attack_rps_per_attacker = attack_aggregate_rps / COMBINED_ATTACK_NUM_ATTACKERS
                    cmd_args = [
                        "--normal-rps", str(normal_rps_per_client),
                        "--rps", str(attack_rps_per_attacker),
                        "--attackers", str(COMBINED_ATTACK_NUM_ATTACKERS),
                        "--work-units", str(wu),
                        "--normal-work-units", str(COMBINED_NORMAL_WORK_UNITS),
                        "--duration", "180",
                    ]
                    if rep == 1:
                        # rep1 substitui o único run antigo (sem sufixo _repN) -- backup do nome antigo.
                        backup_existing(dir_path, f"{scenario}_atk{pct}pct_wu{wu}")
                    run_and_collect(cmd_args, dir_path, suffix,
                                     save_attack_summary=True, save_normal_summary=True)
    return n


# ---------------------------------------------------------------------------
# atacantes_intensidade_grid -- reaproveita run_atacantes_intensidade_grid.run_point()
# ---------------------------------------------------------------------------
ATK_GRID_NORMAL_SCENARIOS = {"S1": 40, "S2": 100, "S3": 200, "S4": 300,
                              "S5": 20, "S6": 80, "S7": 160, "S8": 320}
ATK_GRID_RE = re.compile(r"^(S\d+)_atk([\d.]+)pct_att(\d+)_wu(\d+)_rep(\d+)$")


def jobs_atacantes_grid(dry_run):
    dir_path = "experiment_results/atacantes_intensidade_grid"
    jobs = []
    for suffix in find_affected(dir_path):
        m = ATK_GRID_RE.match(suffix)
        if not m:
            print(f"[AVISO] atacantes_intensidade_grid: sufixo fora do padrão, pulando: {suffix}")
            continue
        scenario, pct_s, att_s, wu_s, rep_s = m.groups()
        pct = float(pct_s) if "." in pct_s else int(pct_s)
        jobs.append((scenario, ATK_GRID_NORMAL_SCENARIOS[scenario], pct, int(att_s), int(rep_s)))
    for scenario, agg, pct, attackers, rep in jobs:
        suffix = f"{scenario}_atk{pct}pct_att{attackers}_wu{atk_grid.WORK_UNITS}_rep{rep}"
        if dry_run:
            print(f"[DRY-RUN] atacantes_intensidade_grid: {suffix}")
            continue
        backup_existing(dir_path, suffix)
        atk_grid.run_point(scenario, agg, pct, attackers, rep)
    return len(jobs)


# ---------------------------------------------------------------------------
# clients_rps_grid -- normal-only, formula de run_experiments_clients_rps.py
# ---------------------------------------------------------------------------
CLIENTS_RE = re.compile(r"^agg(\d+)_clients(\d+)_WU(\d+)_rep(\d+)$")


def jobs_clients_rps_grid(dry_run):
    dir_path = "experiment_results/clients_rps_grid"
    n = 0
    for suffix in find_affected(dir_path):
        m = CLIENTS_RE.match(suffix)
        if not m:
            print(f"[AVISO] clients_rps_grid: sufixo fora do padrão, pulando: {suffix}")
            continue
        agg, clients, wu, rep = (int(x) for x in m.groups())
        n += 1
        if dry_run:
            print(f"[DRY-RUN] clients_rps_grid: {suffix}")
            continue
        rps_per_client = agg / clients
        cmd_args = [
            "--normal-rps", str(rps_per_client),
            "--normal-clients", str(clients),
            "--normal-work-units", str(wu),
            "--attack-duration", "0",
            "--duration", "180",
        ]
        backup_existing(dir_path, suffix)
        run_and_collect(cmd_args, dir_path, suffix,
                         save_attack_summary=False, save_normal_summary=True)
    return n


# ---------------------------------------------------------------------------
# desempate_combinado_isolado -- formula de run_desempate_combinado_isolado.py
# (e run_desempate_rps1.py p/ rps=1, mesma convenção de nome/CLI)
# ---------------------------------------------------------------------------
DESEMPATE_RE = re.compile(r"^(combinado|isolado)_rps([\d.]+)_att(\d+)_WU(\d+)_rep(\d+)$")


def jobs_desempate(dry_run):
    dir_path = "experiment_results/desempate_combinado_isolado"
    n = 0
    for suffix in find_affected(dir_path):
        m = DESEMPATE_RE.match(suffix)
        if not m:
            print(f"[AVISO] desempate_combinado_isolado: sufixo fora do padrão, pulando: {suffix}")
            continue
        condicao, rps_s, att_s, wu_s, rep_s = m.groups()
        rps = float(rps_s) if "." in rps_s else int(rps_s)
        attackers, wu, rep = int(att_s), int(wu_s), int(rep_s)
        n += 1
        if dry_run:
            print(f"[DRY-RUN] desempate_combinado_isolado: {suffix}")
            continue
        normal_rps = "10" if condicao == "combinado" else "0"
        cmd_args = [
            "--rps", str(rps),
            "--attackers", str(attackers),
            "--work-units", str(wu),
            "--normal-rps", normal_rps,
            "--duration", "180",
        ]
        backup_existing(dir_path, suffix)
        run_and_collect(cmd_args, dir_path, suffix,
                         save_attack_summary=True,
                         save_normal_summary=(condicao == "combinado"))
    return n


# ---------------------------------------------------------------------------
# normal_baseline -- 4 sub-formulas verificadas contra os scripts reais
# (run_graph4_refined.py, run_experiments_normal.py, wedos_repro_test.py; 2
# scripts já deletados, mas convenção de nome verificada e consistente com
# os irmãos que sobreviveram -- ver relatório na conversa).
# ---------------------------------------------------------------------------
NB_REFINED_RE = re.compile(r"^normal_agg(\d+)_WU(\d+)_refined_rep(\d+)$")
NB_THR_AGG_RE = re.compile(r"^normal_rps([\d.]+)_WU(\d+)_thr_agg\d+_rep(\d+)$")
NB_PLAIN_REP_RE = re.compile(r"^normal_rps([\d.]+)_WU(\d+)_rep(\d+)$")
NB_PLAIN_RE = re.compile(r"^normal_rps([\d.]+)_WU(\d+)$")
NB_REPRO_RE = re.compile(r"^normal_rps75_WU10_repro_lote([AB])_rep(\d+)$")


def jobs_normal_baseline(dry_run):
    dir_path = "experiment_results/normal_baseline"
    n = 0
    for suffix in find_affected(dir_path):
        rps = wu = None
        if m := NB_REFINED_RE.match(suffix):
            agg, wu_s, rep_s = m.groups()
            rps, wu, rep = int(agg) / 4, int(wu_s), int(rep_s)
        elif m := NB_THR_AGG_RE.match(suffix):
            rps_s, wu_s, rep_s = m.groups()
            rps, wu, rep = float(rps_s), int(wu_s), int(rep_s)
        elif m := NB_REPRO_RE.match(suffix):
            lote, rep_s = m.groups()
            rps, wu, rep = 75, 10, int(rep_s)
        elif m := NB_PLAIN_REP_RE.match(suffix):
            rps_s, wu_s, rep_s = m.groups()
            rps, wu, rep = float(rps_s), int(wu_s), int(rep_s)
        elif m := NB_PLAIN_RE.match(suffix):
            rps_s, wu_s = m.groups()
            rps, wu, rep = float(rps_s), int(wu_s), None
        else:
            print(f"[AVISO] normal_baseline: sufixo fora do padrão, pulando: {suffix}")
            continue

        n += 1
        if dry_run:
            print(f"[DRY-RUN] normal_baseline: {suffix}  (normal-rps={rps}, WU={wu})")
            continue
        cmd_args = [
            "--normal-rps", str(rps),
            "--normal-work-units", str(wu),
            "--attack-duration", "0",
            "--duration", "180",
        ]
        backup_existing(dir_path, suffix)
        run_and_collect(cmd_args, dir_path, suffix,
                         save_attack_summary=False, save_normal_summary=True)
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    builders = [
        ("wedos_grid", jobs_wedos_grid),
        ("combined_sweep", jobs_combined_sweep),
        ("atacantes_intensidade_grid", jobs_atacantes_grid),
        ("clients_rps_grid", jobs_clients_rps_grid),
        ("desempate_combinado_isolado", jobs_desempate),
        ("normal_baseline", jobs_normal_baseline),
    ]

    total = 0
    for name, fn in builders:
        print(f"\n===== {name} =====")
        count = fn(args.dry_run)
        print(f"  -> {count} execuções" + (" planejadas" if args.dry_run else " concluídas"))
        total += count

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Total: {total} execuções")


if __name__ == "__main__":
    main()
