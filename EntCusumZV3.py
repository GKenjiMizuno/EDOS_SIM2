import pandas as pd
import numpy as np
from scipy import stats
import os
import matplotlib.pyplot as plt
import config

# --- Z-score e entropia NOVOS (changes.txt §138), calibrados no §138 com o
# protocolo do §129 (calibracao_z_entropia.py). Parâmetros recomendados:
Z_K_RECOMENDADO = 15.0          # z robusto = (x - mediana_base) / (1,4826 · MAD_base)
Z_FRAC_RECOMENDADA = 0.019      # janela alarma se > 1,9% das amostras tiverem z > k
ENTROPIA_BINS_RECOMENDADO = 10  # faixas log-espaçadas entre mín. e p99,9 do baseline (+1 de transbordo)
ENTROPIA_JS_RECOMENDADO = 0.078  # janela alarma se JS(janela || baseline) > limiar (base 2, 0..1)


def bordas_log_baseline(baseline_vals, n_bins=ENTROPIA_BINS_RECOMENDADO):
    """n_bins faixas log entre o mín. e o p99,9 do baseline + 1 faixa de transbordo (> p99,9).
    Devolve as bordas inferiores de cada faixa (len = n_bins + 1)."""
    b = np.asarray(baseline_vals, dtype=float)
    lo, hi = max(b.min(), 1e-3), np.percentile(b, 99.9)
    return np.concatenate([np.geomspace(lo, hi, n_bins + 1)[:-1], [hi]])


def histograma_faixas(vals, bordas):
    """Proporção por faixa; abaixo do mín. vai para a 1ª, acima do p99,9 para o transbordo."""
    idx = np.clip(np.searchsorted(bordas, np.asarray(vals, dtype=float), side="right") - 1, 0, len(bordas) - 1)
    c = np.bincount(idx, minlength=len(bordas)).astype(float)
    return c / c.sum()


def entropia_shannon(p):
    p = np.asarray(p)[np.asarray(p) > 0]
    return float(-(p * np.log2(p)).sum())


def divergencia_js(p, q):
    """Jensen-Shannon (base 2, entre 0 e 1) = H(M) - (H(P) + H(Q)) / 2, M = (P + Q) / 2."""
    p, q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)
    return entropia_shannon(0.5 * (p + q)) - 0.5 * (entropia_shannon(p) + entropia_shannon(q))


def z_robusto_params(baseline_vals):
    """(mediana, escala) do baseline para o z robusto; escala = 1,4826 · MAD (cai no desvio se MAD = 0)."""
    b = np.asarray(baseline_vals, dtype=float)
    med = np.median(b)
    esc = 1.4826 * np.median(np.abs(b - med))
    return med, (esc if esc > 0 else b.std())


def analisar_bursts_tunavel(input_file='rtt_log.csv', output_prefix=None,
                             window_seconds=20, overlap_percent=50,
                             z_threshold=3.5, baseline_ratio=1.8, show_plot=True,
                             time_col='timestamp', value_col='rtt', value_label='RTT',
                             value_unit='ms', min_samples_per_window=10, cusum_h_sigma=5.0,
                             z_modo='janela_anterior', z_k=Z_K_RECOMENDADO, z_frac=Z_FRAC_RECOMENDADA,
                             entropia_modo='arquivo', entropia_bins=ENTROPIA_BINS_RECOMENDADO,
                             entropia_limiar=ENTROPIA_JS_RECOMENDADO):
    """
    Detector de burst por janela deslizante (entropia de Shannon + Z-score +
    CUSUM) sobre uma série temporal escalar qualquer -- por padrão RTT
    (rtt_log.csv), mas generalizado (changes.txt) para aceitar também CPU
    (simulation_metrics.csv: time_col='elapsed_time_s', value_col=
    'average_cpu_percent' ou 'host_cpu_percent') via os parâmetros
    time_col/value_col/value_label/value_unit. Os nomes de coluna de SAÍDA
    (xlsx) só mudam se value_label for alterado -- com os defaults (RTT),
    ficam idênticos aos de sempre ("Média RTT", "Status Burst", etc.),
    porque generate_presentation_graphs.py/wedos_graphs.py/
    wedos_ent_cusum_report.py leem esses nomes literalmente.

    z_modo (§138): 'janela_anterior' (padrão, comportamento original: maior
    |z| da janela contra média/desvio da janela anterior > z_threshold) ou
    'robusto_baseline' (z = (x - mediana_base)/(1,4826·MAD_base); alarme se a
    fração de amostras com z > z_k passar de z_frac). O original dispara em
    ~99% das janelas sem ataque (milhares de amostras/janela + cauda pesada).
    entropia_modo (§138): 'arquivo' (padrão, original: 10 faixas lineares do
    mín. ao máx. do arquivo; ΔH contra a janela anterior > 1,5 -- degenerado,
    91-99% das amostras na 1ª faixa) ou 'js_baseline' (entropia_bins faixas
    log entre mín. e p99,9 do baseline + transbordo; alarme se a divergência
    de Jensen-Shannon janela x baseline passar de entropia_limiar).
    Os padrões preservam o comportamento original (resultados antigos
    reproduzíveis); os valores recomendados estão nas constantes do módulo.

    min_samples_per_window: mínimo de amostras dentro da janela para ela
    ser analisada (janelas mais esparsas são puladas). RTT tem uma linha
    por requisição (dezenas a centenas por janela de 20s) -- o default 10
    é adequado. CPU tem só 1 linha a cada
    config.MONITOR_INTERVAL_SECONDS (~5s) -- para não descartar toda
    janela, use um window_seconds maior (~50-60s) e/ou um
    min_samples_per_window menor (~5) ao chamar com dado de CPU.
    """
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
        df = df.sort_values(time_col).reset_index(drop=True)
        ts_inicial = df[time_col].min()
        df['tempo_rel'] = df[time_col] - ts_inicial

        stride_seconds = window_seconds * (1 - overlap_percent / 100)
        delta_entropia_threshold = 1.5

        resultados = []
        stats_anterior = None
        entropia_anterior = None

        # Baseline = amostras antes do ataque começar (config.ATTACK_START_TIME_
        # SECONDS), em vez de estatísticas do arquivo INTEIRO (que misturava
        # período de ataque no próprio "normal" de referência, subestimando o
        # quão anômalo o ataque realmente é). Serve tanto de referência para o
        # CUSUM (substitui o global_mean/global_std antigo) quanto para o piso
        # de burst logo abaixo.
        baseline = df.loc[df['tempo_rel'] < config.ATTACK_START_TIME_SECONDS, value_col]
        if len(baseline) >= 10:
            global_mean, global_std = baseline.mean(), baseline.std()
        else:
            print(f"[WARNING] Poucas amostras antes do ataque (t<{config.ATTACK_START_TIME_SECONDS}s): "
                  f"{len(baseline)}. Usando o arquivo inteiro como baseline (menos preciso).")
            global_mean, global_std = df[value_col].mean(), df[value_col].std()
        # cusum_h_sigma: limiar do CUSUM em múltiplos do desvio do baseline.
        # Default 5 preserva o comportamento original (todos os resultados
        # antigos continuam reproduzíveis). Com RTT por requisição (milhares
        # de amostras/janela, cauda pesada) 5σ dispara em 47-93% das execuções
        # sem ataque; ~1000σ é a calibração medida em changes.txt §124-§125.
        kappa, h = 0.5 * global_std, cusum_h_sigma * global_std

        # Piso de burst relativo ao baseline desta execução, em vez de um
        # valor fixo igual para todo cenário (RPS/WU diferentes têm nível
        # "normal" bem diferente entre si — um piso fixo não separa bem os
        # dois). Não usamos média+k*desvio aqui porque só há ~20s de dado
        # limpo antes do ataque (1 janela), amostra pequena demais para
        # estimar desvio-padrão de janela com confiança — a razão sobre a
        # média (mais estável) funciona melhor com essa quantidade de dado.
        valor_threshold = global_mean * baseline_ratio
        if z_modo == 'robusto_baseline':
            z_med, z_esc = z_robusto_params(baseline)
        if entropia_modo == 'js_baseline':
            bordas_ent = bordas_log_baseline(baseline, entropia_bins)
            p_base = histograma_faixas(baseline, bordas_ent)
        print(f"[INFO] Baseline pré-ataque: média={global_mean:.1f}{value_unit}, "
              f"desvio={global_std:.1f}{value_unit} ({len(baseline)} amostras) "
              f"-> piso de burst = {valor_threshold:.1f}{value_unit} ({baseline_ratio}x a média)")

        # CUSUM -- precomputado 1x por amostra bruta, em ORDEM TEMPORAL, antes
        # do laço de janelas (não reprocessado por janela como antes: com
        # sobreposição de janela > 0, cada amostra aparecia em mais de uma
        # janela, e o laço antigo a somava de novo em cada uma, inflando o
        # CUSUM e tornando sua taxa de crescimento dependente de
        # overlap_percent -- um parâmetro que deveria só controlar
        # granularidade da janela, não sensibilidade de detecção. Bug
        # corrigido, ver changes.txt). Cada janela do relatório abaixo só LÊ
        # o valor já acumulado na última amostra dentro dela.
        cusum_running = np.empty(len(df))
        c = 0.0
        for idx, val in enumerate(df[value_col].values):
            c = max(0.0, c + (val - global_mean) - kappa)
            cusum_running[idx] = c
        df['_cusum_running'] = cusum_running

        # Faixa fixa do histograma de entropia (min/max do arquivo inteiro,
        # não da janela individual) -- antes cada janela recalculava seus
        # próprios limites de bin a partir do próprio min/max, então a
        # "resolução" dos 10 bins mudava de janela pra janela, tornando a
        # entropia não comparável entre elas. Usar o min/max do ARQUIVO
        # INTEIRO (não só do baseline pré-ataque) evita também o problema de
        # np.histogram descartar silenciosamente amostras fora do range
        # informado -- se o range viesse só do baseline, picos de RTT/CPU
        # durante o ataque (fora da faixa "normal") seriam excluídos da
        # contagem em vez de aparecer no bin mais alto, distorcendo a
        # entropia bem no momento que mais interessa medir.
        val_min, val_max = df[value_col].min(), df[value_col].max()

        t_start = 0.0
        while t_start < df['tempo_rel'].max():
            t_end = t_start + window_seconds
            janela_mask = (df['tempo_rel'] >= t_start) & (df['tempo_rel'] < t_end)
            janela = df.loc[janela_mask]

            if len(janela) < min_samples_per_window:
                t_start += stride_seconds
                continue

            ts_aprox_rel = janela['tempo_rel'].mean()
            tempo_formatado = f"{int(ts_aprox_rel // 60):02d}:{ts_aprox_rel % 60:05.1f}"

            valor_medio = janela[value_col].mean()
            valor_std = janela[value_col].std()

            # Entropia
            if entropia_modo == 'js_baseline':
                p_jan = histograma_faixas(janela[value_col].values, bordas_ent)
                entropia = entropia_shannon(p_jan)
                delta_entropia = divergencia_js(p_jan, p_base)  # coluna 'Δ Ent.' = JS neste modo
                alarme_entropia = 'Sim' if delta_entropia > entropia_limiar else 'Não'
            else:
                # Original (faixa de bins fixa do arquivo, ver comentário acima)
                hist, _ = np.histogram(janela[value_col], bins=10, range=(val_min, val_max), density=True)
                probs = hist / np.sum(hist) if np.sum(hist) > 0 else np.zeros(10)
                entropia = stats.entropy(probs[probs > 0], base=2) if np.any(probs > 0) else 0.0
                delta_entropia = abs(entropia - entropia_anterior) if entropia_anterior is not None else 0.0
                alarme_entropia = 'Sim' if delta_entropia > delta_entropia_threshold else 'Não'
            entropia_anterior = entropia

            # Z-score
            max_z = 0.0
            alarme_z = 'Não'
            if z_modo == 'robusto_baseline':
                zs = (janela[value_col].values - z_med) / z_esc
                max_z = float((zs > z_k).mean())  # coluna 'Max Z' = fração de amostras com z > k neste modo
                alarme_z = 'Sim' if max_z > z_frac else 'Não'
            elif stats_anterior and stats_anterior['std'] > 0:
                zs = np.abs((janela[value_col] - stats_anterior['media']) / stats_anterior['std'])
                max_z = zs.max()
                alarme_z = 'Sim' if max_z > z_threshold else 'Não'

            # CUSUM -- lê o valor já precomputado (ver acima), não reprocessa
            # a janela.
            cusum_atual = janela['_cusum_running'].iloc[-1]
            alarme_cusum = 'Sim' if cusum_atual > h else 'Não'

            # Status Burst (tunável). Entropia é reportada mas NÃO entra
            # nesta decisão (mantido assim de propósito -- combinar os 3
            # sinais sem medir a taxa de falso-positivo de cada um
            # isoladamente primeiro arriscaria piorar a detecção; decisão
            # registrada em changes.txt).
            status = 'DDoS Burst' if valor_medio > valor_threshold and (alarme_z == 'Sim' or alarme_cusum == 'Sim') else 'Normal/Residual'

            resultados.append({
                'Janela (MM:SS.s)': tempo_formatado,
                f'Média {value_label}': f"{valor_medio:.1f}",
                'Std': f"{valor_std:.1f}",
                'Entropia': f"{entropia:.2f}",
                'Δ Ent.': f"{delta_entropia:.4f}" if entropia_modo == 'js_baseline' else f"{delta_entropia:.2f}",
                'Al. Ent.': alarme_entropia,
                'Max Z': f"{max_z:.4f}" if z_modo == 'robusto_baseline' else f"{max_z:.2f}",
                'Al. Z': alarme_z,
                'CUSUM': f"{cusum_atual:.0f}",
                'Al. CUSUM': alarme_cusum,
                'Status Burst': status
            })
            stats_anterior = {'media': valor_medio, 'std': valor_std}
            t_start += stride_seconds

        df_res = pd.DataFrame(resultados)
        print(df_res.to_string(index=False))
        df_res.to_excel(xlsx_path, index=False)

        # Gráfico com bursts destacados
        fig, ax = plt.subplots(figsize=(14,6))
        tempos_seg = [float(row.split(':')[0])*60 + float(row.split(':')[1]) for row in df_res['Janela (MM:SS.s)']]
        col_media = f'Média {value_label}'
        ax.plot(tempos_seg, df_res[col_media].astype(float), 'b-', label=col_media, marker='o')
        bursts = df_res[df_res['Status Burst'] == 'DDoS Burst']
        ax.scatter([tempos_seg[i] for i in bursts.index], bursts[col_media].astype(float), c='r', s=150, marker='X', label='DDoS Bursts Detectados', zorder=5)
        ax.axhline(valor_threshold, color='gray', linestyle='--', alpha=0.6,
                   label=f'Piso de burst ({valor_threshold:.0f}{value_unit})')
        # Janela de ataque lida de config.py em vez de fixa no código, para não
        # ficar desatualizada se ATTACK_START_TIME_SECONDS/PULSE_DURATION mudarem
        # (o ataque agora é uma janela única — ver Fase 1 do roadmap).
        attack_start = config.ATTACK_START_TIME_SECONDS
        attack_end = attack_start + config.PULSE_DURATION
        ax.axvspan(attack_start, attack_end, alpha=0.2, color='orange',
                   label=f'Intervalo Esperado ({attack_start}-{attack_end}s)')
        ax.set_xlabel('Tempo Relativo (s)')
        ax.set_ylabel(f'{col_media} ({value_unit})')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.title(f'Todos os Bursts DDoS (Tunável: Z>{z_threshold}, {value_label}>{baseline_ratio}x baseline)')
        plt.tight_layout()
        plt.savefig(png_path, dpi=300)
        if show_plot:
            plt.show()
        plt.close(fig)

        print(f"\n✅ Bursts detectados: {len(bursts)} | Excel: {xlsx_path} | Gráfico: {png_path}")

        # Retorna o resultado (além de salvar em disco) para permitir uso em
        # lote/scoring sem precisar reabrir o xlsx logo em seguida -- ver
        # scripts de análise estatística (changes.txt).
        return df_res

    except Exception as e:
        print(f"Erro: {e}")
        return None

if __name__ == "__main__":
    analisar_bursts_tunavel(z_threshold=3.5, baseline_ratio=1.8)  # Tune aqui!
