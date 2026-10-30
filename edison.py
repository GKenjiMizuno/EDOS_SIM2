"""
EDiSON — detector W-EDoS por FUSÃO infra + RTT (Sotelo Monge, Maestre Vidal,
Martínez Pérez, 2019, "Detection of economic denial of sustainability (EDoS)
threats in self-organizing networks", Computer Communications 145, 284-308).

Implementa a parte W-EDoS do EDiSON (seções 5.2-5.3 do paper), que decide se um
ataque está em curso observando DUAS métricas ao mesmo tempo:
  - X_cpu : consumo de CPU ao nível do SO (infra);
  - X_app : entropia de Rényi (normalizada) do tempo de resposta (RTT).
Cada série é prevista por Double Exponential Smoothing (DES/Holt, eq. 14-18),
constrói-se um intervalo de previsão adaptativo (PI, eq. 19-20), e uma observação
é "inesperada" quando cai fora do PI (Definição 7). O ALERTA W-EDoS só é emitido
quando, no MESMO instante t, AMBAS as métricas são inesperadas (fusão) — é isso
que filtra o "efeito de ressalto" do limiar adaptativo e separa o W-EDoS de
oscilações benignas.

Este módulo é offline (pós-processamento), como o EntCusumZV3 — não toca no
simulador. Consome metrics_*.csv (X_cpu) e rtt_log_*.csv (X_app).
"""
import numpy as np

from EntCusumZV3 import bordas_log_baseline, entropia_shannon, histograma_faixas

# ---- Parâmetros (fundamentados no paper; ver EDISON_INFRA_RTT.txt) -----------
A_NIVEL = 0.3          # A = constante de suavização do nível (α do SES; renomeado p/ não colidir com α de Rényi)
GAMMA_TEND = 0.05      # γ = constante de suavização da tendência do DES (baixo: evita a tendência "perseguir" o ataque)
ETA = 2.5              # η (= K do paper) calibra a largura do PI; η maior = menos sensível (calibrado: FP baixo no baseline, ~60% dos ataques pegos)
RENYI_ALFA = 1.0       # ordem de Rényi; α=1 => Shannon (melhor AUC no paper: 0,955)
JANELA_ENT_S = 20.0    # janela deslizante (s) p/ a entropia do RTT
ENT_BINS = 10          # faixas log do histograma de RTT (= ENTROPIA_BINS_RECOMENDADO)


def entropia_renyi_norm(vals, bordas, alfa=RENYI_ALFA):
    """H_alfa(X_app) normalizada por log(n) -> [0,1] (eq. 10/11). alfa=1 => Shannon."""
    p = histograma_faixas(vals, bordas)
    n = len(bordas)
    if abs(alfa - 1.0) < 1e-9:
        h = entropia_shannon(p)                       # Shannon, base 2 (eq. 11)
    else:
        pp = p[p > 0]
        h = (1.0 / (1.0 - alfa)) * np.log2((pp ** alfa).sum())  # Rényi (eq. 10)
    return h / np.log2(n) if n > 1 else 0.0


def des_forecast(x, A=A_NIVEL, gamma=GAMMA_TEND, s0=None, b0=None):
    """Double Exponential Smoothing (Holt). Devolve a previsão 1-passo-à-frente
    xhat[t] = S[t-1] + b[t-1] (eq. 17/18 com m=1), o nível S e a tendência b.
    s0/b0 inicializam nível/tendência (default: 1ª amostra e inclinação média, eq. 16)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    S = np.zeros(n)
    b = np.zeros(n)
    xhat = np.full(n, np.nan)
    S[0] = x[0] if s0 is None else s0
    b[0] = ((x[-1] - x[0]) / (n - 1) if n > 1 else 0.0) if b0 is None else b0
    for t in range(1, n):
        xhat[t] = S[t - 1] + b[t - 1]                 # previsão (eq. 17/18, m=1)
        S[t] = A * x[t] + (1 - A) * (S[t - 1] + b[t - 1])          # nível (eq. 14)
        b[t] = gamma * (S[t] - S[t - 1]) + (1 - gamma) * b[t - 1]  # tendência (eq. 15)
    return xhat, S, b


def _serie_no_grid(m, r, grid, base_ini, base_fim):
    """Monta X_cpu e X_app na grade comum `grid` (s). X_cpu = CPU média por instância
    interpolada na grade; X_app = entropia de Rényi do RTT na janela [t-JANELA, t)."""
    x_cpu = np.interp(grid, m.elapsed_time_s.values, m.average_cpu_percent.values)
    rt, rv = r.t.values, r.rtt.values
    base = rv[(rt >= base_ini) & (rt < base_fim)]
    if len(base) < 10:
        base = rv[rt < base_fim]
    bordas = bordas_log_baseline(base, ENT_BINS)
    x_app = np.full(len(grid), np.nan)
    for i, t in enumerate(grid):
        w = rv[(rt >= t - JANELA_ENT_S) & (rt < t)]
        if len(w) >= 5:
            x_app[i] = entropia_renyi_norm(w, bordas)
    # preenche buracos iniciais com a 1ª entropia válida (warmup do DES)
    if np.isnan(x_app).any():
        valido = np.where(~np.isnan(x_app))[0]
        if len(valido):
            x_app[:valido[0]] = x_app[valido[0]]
            x_app = _ffill(x_app)
    return x_cpu, x_app


def _ffill(a):
    a = a.copy()
    for i in range(1, len(a)):
        if np.isnan(a[i]):
            a[i] = a[i - 1]
    return a


def _detecta_serie(x, idx_base, lado, A, gamma, eta):
    """Previsão DES + PI adaptativo p/ UMA série. `lado`: 'cima' (CPU: inesperado só
    acima), 'ambos' (app: qualquer lado). idx_base = índices da grade no baseline.
    Devolve xhat, PI inferior/superior e máscara de observações inesperadas."""
    # init de nível/tendência a partir do baseline (sem espiar o futuro)
    if len(idx_base) >= 2:
        s0 = x[idx_base[0]]
        b0 = (x[idx_base[-1]] - x[idx_base[0]]) / (idx_base[-1] - idx_base[0])
    else:
        s0, b0 = x[0], 0.0
    xhat, _, _ = des_forecast(x, A=A, gamma=gamma, s0=s0, b0=b0)
    # σ do erro de previsão estimado SÓ no baseline (eq. 20: η·√σ²(ε_t))
    err_base = (x[idx_base] - xhat[idx_base])
    err_base = err_base[~np.isnan(err_base)]
    sigma = err_base.std() if len(err_base) > 1 else np.nanstd(x - xhat)
    sigma = sigma if sigma > 1e-9 else (np.nanstd(x) or 1.0)
    pi_lo = xhat - eta * sigma
    pi_hi = xhat + eta * sigma
    if lado == "cima":
        inesper = x > pi_hi
    else:
        inesper = (x > pi_hi) | (x < pi_lo)
    inesper = inesper & ~np.isnan(xhat)
    return xhat, pi_lo, pi_hi, inesper, sigma


def detectar(m, r, base_ini=60, base_fim=300, passo=5.0,
             A=A_NIVEL, gamma=GAMMA_TEND, eta=ETA):
    """Executa o EDiSON W-EDoS. Devolve um dict com a grade, as duas séries, suas
    previsões/PI/máscaras e o ALERTA fundido (ambas inesperadas no mesmo t)."""
    t0, t1 = float(m.elapsed_time_s.min()), float(m.elapsed_time_s.max())
    grid = np.arange(max(t0, 0), t1 + 1e-6, passo)
    x_cpu, x_app = _serie_no_grid(m, r, grid, base_ini, base_fim)
    idx_base = np.where((grid >= base_ini) & (grid < base_fim))[0]
    if len(idx_base) < 2:
        idx_base = np.where(grid < base_fim)[0]
    cpu_hat, cpu_lo, cpu_hi, cpu_un, cpu_sig = _detecta_serie(x_cpu, idx_base, "cima", A, gamma, eta)
    app_hat, app_lo, app_hi, app_un, app_sig = _detecta_serie(x_app, idx_base, "ambos", A, gamma, eta)
    alerta = cpu_un & app_un                       # fusão: ambas inesperadas no mesmo t (Def. 7)
    return dict(grid=grid, x_cpu=x_cpu, x_app=x_app,
                cpu_hat=cpu_hat, cpu_lo=cpu_lo, cpu_hi=cpu_hi, cpu_un=cpu_un, cpu_sig=cpu_sig,
                app_hat=app_hat, app_lo=app_lo, app_hi=app_hi, app_un=app_un, app_sig=app_sig,
                alerta=alerta, eta=eta, A=A, gamma=gamma)
