import pandas as pd
import numpy as np
from scipy import stats
import os
import matplotlib.pyplot as plt
import config

def analisar_bursts_tunavel(input_file='rtt_log.csv', output_prefix=None,
                             window_seconds=20, overlap_percent=50,
                             z_threshold=3.5, baseline_ratio=1.8, show_plot=True):
    output_dir = os.path.dirname(input_file)
    base = os.path.splitext(os.path.basename(input_file))[0]
    if output_prefix is None and base == 'rtt_log':
        # Chamado sem argumentos (uso padrão/manual): preserva os nomes de
        # saída originais exatamente como antes.
        xlsx_path = os.path.join(output_dir, 'rtt_bursts_tunaveis.xlsx')
        png_path = os.path.join(output_dir, 'rtt_todos_bursts.png')
    else:
        # Uso em lote (ver run_burst_analysis.py): deriva um sufixo do nome
        # do arquivo de entrada para não sobrescrever a saída de outros runs.
        if output_prefix is None:
            output_prefix = base[len('rtt_log_'):] if base.startswith('rtt_log_') else base
        xlsx_path = os.path.join(output_dir, f'rtt_bursts_{output_prefix}.xlsx')
        png_path = os.path.join(output_dir, f'rtt_todos_bursts_{output_prefix}.png')
    try:
        df = pd.read_csv(input_file)
        df = df.sort_values('timestamp').reset_index(drop=True)
        ts_inicial = df['timestamp'].min()
        df['tempo_rel'] = df['timestamp'] - ts_inicial
        
        stride_seconds = window_seconds * (1 - overlap_percent / 100)
        delta_entropia_threshold = 1.5

        resultados = []
        stats_anterior = None
        cusum_atual = 0.0
        entropia_anterior = None

        # Baseline = amostras antes do ataque começar (config.ATTACK_START_TIME_
        # SECONDS), em vez de estatísticas do arquivo INTEIRO (que misturava
        # período de ataque no próprio "normal" de referência, subestimando o
        # quão anômalo o ataque realmente é). Serve tanto de referência para o
        # CUSUM (substitui o global_mean/global_std antigo) quanto para o piso
        # de RTT do burst logo abaixo.
        baseline = df.loc[df['tempo_rel'] < config.ATTACK_START_TIME_SECONDS, 'rtt']
        if len(baseline) >= 10:
            global_mean, global_std = baseline.mean(), baseline.std()
        else:
            print(f"[WARNING] Poucas amostras antes do ataque (t<{config.ATTACK_START_TIME_SECONDS}s): "
                  f"{len(baseline)}. Usando o arquivo inteiro como baseline (menos preciso).")
            global_mean, global_std = df['rtt'].mean(), df['rtt'].std()
        kappa, h = 0.5 * global_std, 5 * global_std

        # Piso de RTT do burst relativo ao baseline desta execução, em vez de um
        # valor fixo em ms igual para todo cenário (RPS/WU diferentes têm RTT
        # "normal" bem diferente entre si — um piso fixo não separa bem os dois).
        # Não usamos média+k*desvio aqui porque só há ~20s de dado limpo antes
        # do ataque (1 janela), amostra pequena demais para estimar desvio-padrão
        # de janela com confiança — a razão sobre a média (mais estável) funciona
        # melhor com essa quantidade de dado.
        rtt_threshold = global_mean * baseline_ratio
        print(f"[INFO] Baseline pré-ataque: média={global_mean:.1f}ms, desvio={global_std:.1f}ms "
              f"({len(baseline)} amostras) -> piso de burst = {rtt_threshold:.1f}ms "
              f"({baseline_ratio}x a média)")

        t_start = 0.0
        while t_start < df['tempo_rel'].max():
            t_end = t_start + window_seconds
            janela_mask = (df['tempo_rel'] >= t_start) & (df['tempo_rel'] < t_end)
            janela = df.loc[janela_mask]
            
            if len(janela) < 10:
                t_start += stride_seconds
                continue
            
            ts_aprox_rel = janela['tempo_rel'].mean()
            tempo_formatado = f"{int(ts_aprox_rel // 60):02d}:{ts_aprox_rel % 60:05.1f}"
            
            media_rtt = janela['rtt'].mean()
            std_rtt = janela['rtt'].std()
            
            # Entropia (como antes)
            hist, _ = np.histogram(janela['rtt'], bins=10, density=True)
            probs = hist / np.sum(hist) if np.sum(hist) > 0 else np.zeros(10)
            entropia = stats.entropy(probs[probs > 0], base=2) if np.any(probs > 0) else 0.0
            delta_entropia = abs(entropia - entropia_anterior) if entropia_anterior is not None else 0.0
            alarme_entropia = 'Sim' if delta_entropia > delta_entropia_threshold else 'Não'
            entropia_anterior = entropia
            
            # Z-score tunável
            max_z = 0.0
            alarme_z = 'Não'
            if stats_anterior and stats_anterior['std'] > 0:
                zs = np.abs((janela['rtt'] - stats_anterior['media']) / stats_anterior['std'])
                max_z = zs.max()
                alarme_z = 'Sim' if max_z > z_threshold else 'Não'
            
            # CUSUM
            for rtt in janela['rtt']:
                cusum_atual = max(0, cusum_atual + (rtt - global_mean) - kappa)
            alarme_cusum = 'Sim' if cusum_atual > h else 'Não'
            
            # Status Burst (tunável)
            status = 'DDoS Burst' if media_rtt > rtt_threshold and (alarme_z == 'Sim' or alarme_cusum == 'Sim') else 'Normal/Residual'
            
            resultados.append({
                'Janela (MM:SS.s)': tempo_formatado,
                'Média RTT': f"{media_rtt:.1f}",
                'Std': f"{std_rtt:.1f}",
                'Entropia': f"{entropia:.2f}",
                'Δ Ent.': f"{delta_entropia:.2f}",
                'Al. Ent.': alarme_entropia,
                'Max Z': f"{max_z:.2f}",
                'Al. Z': alarme_z,
                'CUSUM': f"{cusum_atual:.0f}",
                'Al. CUSUM': alarme_cusum,
                'Status Burst': status
            })
            stats_anterior = {'media': media_rtt, 'std': std_rtt}
            t_start += stride_seconds
        
        df_res = pd.DataFrame(resultados)
        print(df_res.to_string(index=False))
        df_res.to_excel(xlsx_path, index=False)
        
        # Gráfico com bursts destacados
        fig, ax = plt.subplots(figsize=(14,6))
        tempos_seg = [float(row.split(':')[0])*60 + float(row.split(':')[1]) for row in df_res['Janela (MM:SS.s)']]
        ax.plot(tempos_seg, df_res['Média RTT'].astype(float), 'b-', label='Média RTT', marker='o')
        bursts = df_res[df_res['Status Burst'] == 'DDoS Burst']
        ax.scatter([tempos_seg[i] for i in bursts.index], bursts['Média RTT'].astype(float), c='r', s=150, marker='X', label='DDoS Bursts Detectados', zorder=5)
        ax.axhline(rtt_threshold, color='gray', linestyle='--', alpha=0.6,
                   label=f'Piso de burst ({rtt_threshold:.0f}ms)')
        # Janela de ataque lida de config.py em vez de fixa no código, para não
        # ficar desatualizada se ATTACK_START_TIME_SECONDS/PULSE_DURATION mudarem
        # (o ataque agora é uma janela única — ver Fase 1 do roadmap).
        attack_start = config.ATTACK_START_TIME_SECONDS
        attack_end = attack_start + config.PULSE_DURATION
        ax.axvspan(attack_start, attack_end, alpha=0.2, color='orange',
                   label=f'Intervalo Esperado ({attack_start}-{attack_end}s)')
        ax.set_xlabel('Tempo Relativo (s)')
        ax.set_ylabel('Média RTT (ms)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.title(f'Todos os Bursts DDoS (Tunável: Z>{z_threshold}, RTT>{baseline_ratio}x baseline)')
        plt.tight_layout()
        plt.savefig(png_path, dpi=300)
        if show_plot:
            plt.show()
        plt.close(fig)

        print(f"\n✅ Bursts detectados: {len(bursts)} | Excel: {xlsx_path} | Gráfico: {png_path}")
    
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    analisar_bursts_tunavel(z_threshold=3.5, baseline_ratio=1.8)  # Tune aqui!