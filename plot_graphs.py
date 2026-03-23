import pandas as pd
import matplotlib.pyplot as plt

# === CONFIG ===
CSV_FILE = "experiment_results/metrics_rps16_att4.csv"
OUTPUT_DIR = "graficos"

import os
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_data():
    df = pd.read_csv(CSV_FILE)
    df = df.sort_values(by="elapsed_time_s")
    return df


def save_plot(fig_name):
    path = f"{OUTPUT_DIR}/{fig_name}.png"
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[OK] Salvo: {path}")


def plot_cpu(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["average_cpu_percent"])
    plt.title("CPU ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("CPU (%)")
    plt.grid()
    save_plot("cpu_tempo")


def plot_instances(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["num_instances"])
    plt.title("Número de instâncias ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Instâncias")
    plt.grid()
    save_plot("instancias_tempo")


def plot_memory(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["mem_usage"])
    plt.title("Uso de memória ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Memória (MB)")
    plt.grid()
    save_plot("memoria_tempo")


def plot_cpu_vs_instances(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["average_cpu_percent"], label="CPU (%)")
    plt.plot(df["elapsed_time_s"], df["num_instances"], label="Instâncias")
    plt.title("CPU vs Instâncias")
    plt.xlabel("Tempo (s)")
    plt.legend()
    plt.grid()
    save_plot("cpu_vs_instancias")


def plot_with_attack_labels(df):
    plt.figure()

    attack = df[df["label"] == "attack"]
    normal = df[df["label"] == "normal"]

    plt.plot(normal["elapsed_time_s"], normal["average_cpu_percent"], label="Normal")
    plt.plot(attack["elapsed_time_s"], attack["average_cpu_percent"], label="Attack")

    plt.title("CPU (Normal vs Ataque)")
    plt.xlabel("Tempo (s)")
    plt.ylabel("CPU (%)")
    plt.legend()
    plt.grid()
    save_plot("cpu_attack_vs_normal")


def main():
    df = load_data()

    plot_cpu(df)
    plot_instances(df)
    plot_memory(df)
    plot_cpu_vs_instances(df)
    plot_with_attack_labels(df)

    print("\n✅ Todos os gráficos foram gerados na pasta 'graficos/'")


if __name__ == "__main__":
    main()