import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Refaz o gráfico 17 (heatmap clientes×RPS) com os dados de
# experiment_results/clients_rps_grid/ já recoletados com a correção do
# load balancer (changes.txt §102-104). Não altera plot_grid_heatmap.py
# nem plot_clients_rps_invariance.py, nem sobrescreve resumo_clients_rps_
# grid.csv (que fica intocado como referência pré-correção) -- recalcula
# o resumo direto dos metrics_*.csv/normal_traffic_summary_log_*.csv
# atuais (100% pós-correção, as 51 configs dessa família foram todas
# recoletadas) e salva num CSV e PNG novos, lado a lado com os originais.
#
# Padrão de nome combinado com o usuário: "<número>_(loadbalancer)".

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "graficos_apresentacao/04_pos_loadbalancer"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]


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

        cpu_c_vals = []
        for mf in metric_files:
            rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
            suffix = f"agg{agg}_clients{clients}_WU10_rep{rep}"
            sf = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
            if not os.path.exists(sf):
                continue
            cpu_c, cpu_h, err_rate, achieved, incomplete = run_stats(mf, sf)
            if incomplete:
                continue
            cpu_c_vals.append(cpu_c)

        if not cpu_c_vals:
            continue

        max_inst = 0
        for mf in metric_files:
            max_inst = max(max_inst, pd.read_csv(mf)["num_instances"].max())

        rows.append(dict(
            target_aggregate=agg, clients=clients, n=len(cpu_c_vals),
            cpu_container_mean=stats.mean(cpu_c_vals),
            max_instances=max_inst,
        ))

if not rows:
    raise SystemExit("Nenhum dado encontrado em experiment_results/clients_rps_grid/.")

df = pd.DataFrame(rows)
csv_out = os.path.join(GRID_DIR, "resumo_clients_rps_grid_loadbalancer.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")

matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), np.nan)
n_matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), 0)
max_inst_matrix = np.full((len(AGGREGATE_TARGETS), len(CLIENT_COUNTS)), 0)
for _, row in df.iterrows():
    i = AGGREGATE_TARGETS.index(int(row["target_aggregate"]))
    j = CLIENT_COUNTS.index(int(row["clients"]))
    matrix[i, j] = row["cpu_container_mean"]
    n_matrix[i, j] = row["n"]
    max_inst_matrix[i, j] = row["max_instances"]

fig, ax = plt.subplots(figsize=(9, 8))
im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", origin="upper", vmin=0, vmax=np.nanmax(matrix))

ax.set_xticks(range(len(CLIENT_COUNTS)))
ax.set_xticklabels([f"{c} cliente(s)" for c in CLIENT_COUNTS])
ax.set_yticks(range(len(AGGREGATE_TARGETS)))
ax.set_yticklabels([f"{a} RPS" for a in AGGREGATE_TARGETS])
ax.set_xlabel("nº de clientes (decomposição)")
ax.set_ylabel("RPS agregado alvo")

for i in range(len(AGGREGATE_TARGETS)):
    for j in range(len(CLIENT_COUNTS)):
        val = matrix[i, j]
        if np.isnan(val):
            continue
        n = n_matrix[i, j]
        rps_per_client = AGGREGATE_TARGETS[i] / CLIENT_COUNTS[j]
        rps_str = f"{rps_per_client:g} rps/cli"
        max_inst = int(max_inst_matrix[i, j])
        color = "white" if val > np.nanmax(matrix) * 0.6 else "black"
        label = f"{val:.1f}%\n{rps_str}\nmáx {max_inst} inst."
        if n != 5:
            label += f" (n={n})"
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=8)

cbar = fig.colorbar(im, ax=ax, label="CPU média do container (%)")
cbar.ax.invert_yaxis()

ax.set_title(
    "Grid clientes×RPS -- CPU média por célula -- pós-correção do load balancer\n"
    "(changes.txt §102-104) -- cada LINHA deveria ficar com cor uniforme"
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "17_grid_heatmap_cpu_(loadbalancer).png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
