import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Refaz o gráfico 11 com os dados de experiment_results/clients_rps_grid/ já
# recoletados com a correção do load balancer (changes.txt §102-104). Não
# altera plot_clients_rps_invariance.py nem o resumo_clients_rps_grid.csv
# original -- reimplementa a mesma lógica (idêntica a
# plot_grid_heatmap_loadbalancer.py, que já recalcula esse resumo pro
# gráfico 17) e salva no diretório dedicado
# graficos_apresentacao/04_pos_loadbalancer/.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]
COLORS = {1: "#2a78d6", 2: "#1baf7a", 4: "#e08a1e", 8: "#d03b3b", 16: "#7a3fd6"}
MARKERS = {1: "o", 2: "s", 4: "^", 8: "D", 16: "v"}


def run_stats(metrics_path, summary_path):
    df = pd.read_csv(metrics_path).iloc[1:]
    cpu_container = df["average_cpu_percent"].mean()
    cpu_host = df["host_cpu_percent"].mean() if "host_cpu_percent" in df.columns else float("nan")

    raw = pd.read_csv(summary_path)
    expected_clients = raw["num_clients"].dropna().iloc[0] if raw["num_clients"].notna().any() else None
    sdf = raw[raw["total_requests"].notna()]
    ok = sdf["total_requests"].sum()
    err = sdf["errors"].sum()
    achieved_rps = sdf["real_rps"].sum()
    err_rate = 100.0 * err / (ok + err) if (ok + err) > 0 else float("nan")
    incomplete = expected_clients is not None and len(sdf) < expected_clients

    return cpu_container, cpu_host, err_rate, achieved_rps, incomplete


rows = []
for agg in AGGREGATE_TARGETS:
    for clients in CLIENT_COUNTS:
        pattern = os.path.join(GRID_DIR, f"metrics_agg{agg}_clients{clients}_WU10_rep*.csv")
        metric_files = sorted(glob.glob(pattern))
        if not metric_files:
            print(f"[WARNING] Sem dados para agregado={agg}, clientes={clients} -- pulando.")
            continue

        cpu_c_vals, cpu_h_vals, err_vals, achieved_vals = [], [], [], []
        incomplete_reps = []
        for mf in metric_files:
            rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
            suffix = f"agg{agg}_clients{clients}_WU10_rep{rep}"
            sf = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
            if not os.path.exists(sf):
                continue
            cpu_c, cpu_h, err_rate, achieved, incomplete = run_stats(mf, sf)
            if incomplete:
                incomplete_reps.append(rep)
                continue
            cpu_c_vals.append(cpu_c)
            cpu_h_vals.append(cpu_h)
            err_vals.append(err_rate)
            achieved_vals.append(achieved)

        if not cpu_c_vals:
            continue

        err_valid = [v for v in err_vals if v == v]

        rows.append(dict(
            target_aggregate=agg, clients=clients, n=len(cpu_c_vals),
            achieved_aggregate_mean=stats.mean(achieved_vals),
            cpu_container_mean=stats.mean(cpu_c_vals),
            cpu_container_std=stats.stdev(cpu_c_vals) if len(cpu_c_vals) > 1 else 0.0,
            cpu_host_mean=stats.mean(cpu_h_vals),
            error_rate_mean=stats.mean(err_valid) if err_valid else float("nan"),
            error_rate_std=stats.stdev(err_valid) if len(err_valid) > 1 else 0.0,
            error_rate_n=len(err_valid),
        ))

if not rows:
    raise SystemExit("Nenhum dado encontrado em experiment_results/clients_rps_grid/.")

df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print(df.to_string(index=False))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("target_aggregate")
    if sub.empty:
        continue
    ax1.errorbar(sub["target_aggregate"], sub["cpu_container_mean"], yerr=sub["cpu_container_std"],
                 fmt=f"{MARKERS[clients]}-", color=COLORS[clients], markersize=8, linewidth=1.8,
                 capsize=4, label=f"{clients} cliente(s)")

ax1.set_xscale("log", base=2)
ax1.set_xticks(AGGREGATE_TARGETS)
ax1.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax1.axhline(60, color="#d03b3b", linestyle=":", linewidth=1, label="limiar SCALE_UP (60%)")
ax1.set_xlabel("RPS agregado alvo (WU=10, escala log2)")
ax1.set_ylabel("CPU média do container (%) ± desvio")
ax1.set_title("CPU média por decomposição clientes×RPS\n(pontos do mesmo agregado deveriam coincidir)")
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3)

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("target_aggregate")
    if sub.empty:
        continue
    ax2.errorbar(sub["target_aggregate"], sub["error_rate_mean"], yerr=sub["error_rate_std"],
                 fmt=f"{MARKERS[clients]}-", color=COLORS[clients], markersize=8, linewidth=1.8,
                 capsize=4, label=f"{clients} cliente(s)")

ax2.set_xscale("log", base=2)
ax2.set_xticks(AGGREGATE_TARGETS)
ax2.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax2.set_xlabel("RPS agregado alvo (WU=10, escala log2)")
ax2.set_ylabel("Taxa de erro média (%) ± desvio")
ax2.set_ylim(0, 1.0)
ax2.set_title("Taxa de erro por decomposição clientes×RPS (escala fixa 0-1%)")
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)

fig.suptitle("Grid clientes×RPS -- RPS agregado é o que importa? (5 repetições/ponto) -- "
             "pós-correção do load balancer (changes.txt §102-104)")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "11_clients_rps_invariancia_(loadbalancer).png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
