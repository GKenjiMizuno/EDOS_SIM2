#!/usr/bin/env bash
# Regenera todos os gráficos de graficos_apresentacao/04_pos_loadbalancer/ a
# partir dos dados versionados em experiment_results/ (changes.txt §140).
# Rodar a partir da raiz do repositório:  bash gerar_graficos_definitivos.sh
# Conferência: bash gerar_graficos_definitivos.sh && md5sum -c MANIFESTO_GRAFICOS.md5
#
# Não roda Docker nem simulação: só lê CSVs. As tabelas intermediárias de
# detecção (experiment_results/deteccao_pos_lb/) já estão versionadas; para
# recalculá-las do zero a partir dos rtt_log brutos, use --completo (mais lento).
set -euo pipefail
cd "$(dirname "$0")"
export MPLBACKEND=Agg

if [[ "${1:-}" == "--completo" ]]; then
    python3 deteccao_pos_lb_extract.py            # janelas/execuções do §117 (windows.csv.gz, runs.csv)
    python3 deteccao_pos_lb_analise.py            # execucoes_avaliadas.csv e tabelas T1-T14
    python3 calibracao_parametros_detectores.py   # T18 (§129)
    python3 calibracao_z_entropia.py              # T20 (§138)
fi

# Gráficos pós-load balancer (recriações "_(loadbalancer)" e novos)
python3 wedos_graphs_loadbalancer.py                                  # 06
python3 plot_clients_rps_invariance_loadbalancer.py                   # 11
python3 plot_grid_heatmap_loadbalancer.py                             # 17
python3 plot_graph4_pico_pre_escalonamento_loadbalancer.py            # 20
python3 plot_normal_referencia_loadbalancer.py                        # 24
python3 plot_normal_referencia_ic_loadbalancer.py                     # 24 com IC 95%
python3 plot_comparacao_completa_v2_loadbalancer.py                   # 27
python3 plot_comparacao_completa_v2_dp_loadbalancer.py                # 27 com DP (sem outliers)
python3 plot_comparacao_completa_v2_dp_loadbalancer.py --com-outliers # 27 com DP (com outliers)
python3 plot_graph4_pow2_base20_quartis_loadbalancer.py               # 42
python3 plot_atacantes_intensidade_grid_loadbalancer.py               # 48
python3 plot_atacantes_intensidade_heatmap_att4_loadbalancer.py       # 55
python3 plot_atacantes_intensidade_grid_pow2_reprodutibilidade_loadbalancer.py  # 56
python3 plot_normal_isolada_teto_loadbalancer.py                      # 57
python3 plot_atacantes_intensidade_heatmap_att4_extended.py           # 58
python3 plot_atacantes_intensidade_heatmap_att4_log2.py               # 58 em 10·2^n
python3 plot_normal_isolado_pos_lb.py                                 # 59, 60, 61
python3 plot_cusum_calibracao.py                                      # 62, 63, 64

# 65-71: detectores por janela (CUSUM, Z, entropia, combinado)
for novos in "" "--novos"; do
    python3 plot_s4_10pct_cpu_rtt_cusum.py $novos                             # 65
    python3 plot_s4_10pct_cpu_rtt_cusum.py --normal $novos                    # 66
    python3 plot_s4_10pct_cpu_rtt_cusum.py --200s --reset $novos              # 67 (reset)
    python3 plot_s4_10pct_cpu_rtt_cusum.py --200s --normal --reset $novos     # 68 (reset)
    for p in 0 1 5; do
        python3 plot_s4_10pct_cpu_rtt_cusum.py --c320=$p $novos               # 69, 70, 71
    done
done
python3 plot_s4_10pct_cpu_rtt_cusum.py --200s                                 # 67 (sem reset)
python3 plot_s4_10pct_cpu_rtt_cusum.py --200s --normal                        # 68 (sem reset)
echo "concluído"
