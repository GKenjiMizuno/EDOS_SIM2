"""
Lote 2 da recoleta pós load balancer (ver changes.txt §102-104 pro lote 1
original, que só pegou os runs AFETADOS -- decision=='SCALE_UP' em algum
tick). Este script pega o COMPLEMENTO: todo run que NUNCA escalou (portanto
nunca entrou no lote original) e que ainda está com dado gerado antes da
correção -- 1 execução (1 rep) por config, substituindo o arquivo antigo,
mesmos parâmetros originais (reaproveita as mesmas fórmulas/regex/funções
de run_scaling_affected_rerun.py, importado como módulo).

Motivação: usuário notou, ao investigar um caso didático (agg512/clients1,
clients_rps_grid), que mesmo runs que NUNCA escalaram -- onde o bug do load
balancer não tem como ter agido, já que só existe 1 instância o tempo
inteiro -- podem mostrar diferenças grandes e não explicadas por código
entre o dado antigo e um run novo (ver changes.txt, investigação da CPU/RTT
de agg512/clients1 pré vs pós). Hipótese de trabalho: diferença de condição
do ambiente/host entre quando o dado antigo foi coletado e agora, não o
código. Este lote existe pra checar se esse efeito é sistemático em todo o
dataset "nunca escalou" ou foi um caso isolado.

combined_sweep NÃO entra aqui -- já foi 100% recoletado no lote 1 (todas as
24 configs, afetadas ou não, expandidas pra 5 reps, ver changes.txt §104).

Uso:
  python3 run_unaffected_rerun.py --dry-run
  python3 run_unaffected_rerun.py
"""
import argparse
import glob
import os

import run_scaling_affected_rerun as base
import run_normal_isolado_s9_s11 as normal_s9_s11

BACKUP_ROOT = base.BACKUP_ROOT


def find_unaffected(dir_path):
    """Todo metrics_*.csv que está no diretório live mas NÃO está no backup
    pré-correção -- ou seja, nunca foi tocado pela recoleta do lote 1."""
    backup_dir = os.path.join(BACKUP_ROOT, os.path.basename(dir_path))
    unaffected = []
    for f in sorted(glob.glob(os.path.join(dir_path, "metrics_*.csv"))):
        bn = os.path.basename(f)
        if not os.path.exists(os.path.join(backup_dir, bn)):
            suffix = bn[len("metrics_"):-len(".csv")]
            unaffected.append(suffix)
    return unaffected


def jobs_wedos_grid(dry_run):
    dir_path = "experiment_results/wedos_grid"
    jobs = []
    for suffix in find_unaffected(dir_path):
        m = base.WEDOS_RE.match(suffix)
        if not m:
            print(f"[AVISO] wedos_grid: sufixo fora do padrão, pulando: {suffix}")
            continue
        scenario, pct_s, wu_s, tag, rep_s = m.groups()
        pct = float(pct_s) if "." in pct_s else int(pct_s)
        jobs.append((scenario, base.wg.NORMAL_SCENARIOS[scenario], pct, int(wu_s), int(rep_s), tag))
    for scenario, agg, pct, wu, rep, tag in jobs:
        suffix = f"{scenario}_atk{pct}pct_wu{wu}_{tag}_rep{rep}"
        if dry_run:
            print(f"[DRY-RUN] wedos_grid: {suffix}")
            continue
        base.backup_existing(dir_path, suffix)
        base.wg.run_point(scenario, agg, pct, wu, rep=rep, tag=tag)
    return len(jobs)


def jobs_atacantes_grid(dry_run):
    dir_path = "experiment_results/atacantes_intensidade_grid"
    jobs = []
    for suffix in find_unaffected(dir_path):
        m = base.ATK_GRID_RE.match(suffix)
        if not m:
            print(f"[AVISO] atacantes_intensidade_grid: sufixo fora do padrão, pulando: {suffix}")
            continue
        scenario, pct_s, att_s, wu_s, rep_s = m.groups()
        if scenario not in base.ATK_GRID_NORMAL_SCENARIOS:
            # Cenário novo (ex.: S9-S11, run_atacantes_intensidade_grid_s9_s11.py)
            # -- run recém-criado, nunca esteve no backup por ser novo, não por
            # nunca ter sido recoletado. Não pertence a este lote (que só existe
            # pra reprocessar dado ANTIGO). Ignorado silenciosamente, sem AVISO
            # (comportamento esperado, não uma anomalia de sufixo).
            continue
        pct = float(pct_s) if "." in pct_s else int(pct_s)
        jobs.append((scenario, base.ATK_GRID_NORMAL_SCENARIOS[scenario], pct, int(att_s), int(rep_s)))
    for scenario, agg, pct, attackers, rep in jobs:
        suffix = f"{scenario}_atk{pct}pct_att{attackers}_wu{base.atk_grid.WORK_UNITS}_rep{rep}"
        if dry_run:
            print(f"[DRY-RUN] atacantes_intensidade_grid: {suffix}")
            continue
        base.backup_existing(dir_path, suffix)
        base.atk_grid.run_point(scenario, agg, pct, attackers, rep)
    return len(jobs)


def jobs_clients_rps_grid(dry_run):
    dir_path = "experiment_results/clients_rps_grid"
    n = 0
    for suffix in find_unaffected(dir_path):
        m = base.CLIENTS_RE.match(suffix)
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
        base.backup_existing(dir_path, suffix)
        base.run_and_collect(cmd_args, dir_path, suffix,
                              save_attack_summary=False, save_normal_summary=True)
    return n


def jobs_desempate(dry_run):
    dir_path = "experiment_results/desempate_combinado_isolado"
    n = 0
    for suffix in find_unaffected(dir_path):
        m = base.DESEMPATE_RE.match(suffix)
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
        base.backup_existing(dir_path, suffix)
        base.run_and_collect(cmd_args, dir_path, suffix,
                              save_attack_summary=True,
                              save_normal_summary=(condicao == "combinado"))
    return n


def jobs_normal_baseline(dry_run):
    dir_path = "experiment_results/normal_baseline"
    n = 0
    for suffix in find_unaffected(dir_path):
        rps = wu = None
        if m := base.NB_REFINED_RE.match(suffix):
            agg, wu_s, rep_s = m.groups()
            if int(agg) in normal_s9_s11.AGGREGATE_TARGETS:
                # Agregado novo (1280/2560, run_normal_isolado_s9_s11.py) --
                # run recém-criado, nunca esteve no backup por ser novo, não
                # por nunca ter sido recoletado. Ignorado, mesmo motivo do
                # skip de cenário em jobs_atacantes_grid acima.
                continue
            rps, wu, rep = int(agg) / 4, int(wu_s), int(rep_s)
        elif m := base.NB_THR_AGG_RE.match(suffix):
            rps_s, wu_s, rep_s = m.groups()
            rps, wu, rep = float(rps_s), int(wu_s), int(rep_s)
        elif m := base.NB_REPRO_RE.match(suffix):
            lote, rep_s = m.groups()
            rps, wu, rep = 75, 10, int(rep_s)
        elif m := base.NB_PLAIN_REP_RE.match(suffix):
            rps_s, wu_s, rep_s = m.groups()
            rps, wu, rep = float(rps_s), int(wu_s), int(rep_s)
        elif m := base.NB_PLAIN_RE.match(suffix):
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
        base.backup_existing(dir_path, suffix)
        base.run_and_collect(cmd_args, dir_path, suffix,
                              save_attack_summary=False, save_normal_summary=True)
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    builders = [
        ("wedos_grid", jobs_wedos_grid),
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
