"""
Calibração das versões NOVAS do Z-score e da entropia (changes.txt §138),
pedido do orientador ("Z muito sensível", "alterar parâmetros da entropia").
Só tabelas, sem Docker. Mesmo protocolo do §129 (calibracao_parametros_
detectores.py): populações NEG/POS/POS_D de execucoes_avaliadas.csv (sem S9-S11,
sem captura), 13 janelas de 20 s com t0 = 20..140, alarme da execução = >= 1
janela; seleção nas reps ÍMPARES, avaliação nas PARES; faixa aceitável = FPR <=
5% e detecção do dano >= 95% (na seleção). Escolhido = maior índice de
Youden (detecção de TODOS os ataques - FPR) dentro da faixa aceitável; o
centro (log) da faixa é reportado como referência de robustez. (Com esse
critério o CUSUM do §129 daria ~1.800σ, coerente com os 2000σ recomendados lá.)
Tempo do
rtt_log corrigido dos saltos de relógio do WSL2 (§128).

Z NOVO ("robusto contra o baseline, por fração"): para cada requisição,
  z = (RTT - mediana_base) / (1,4826 · MAD_base), baseline = RTT em t < 20 s.
  Janela alarma se a FRAÇÃO de requisições com z > k passar de f.
  (Antes: maior |z| da janela contra a média/desvio da janela ANTERIOR > 3,5.)
ENTROPIA NOVA ("faixas do baseline em escala log"): histograma com nb faixas
  log-espaçadas entre o mín. e o percentil 99,9 do baseline, + 1 faixa de
  transbordo (acima do p99,9) -- valores abaixo do mín. vão para a 1ª faixa.
  Estatísticas: ΔH = |H(janela) - H(baseline)| e divergência de Jensen-Shannon
  JS(janela || baseline) (base 2, entre 0 e 1).
  (Antes: 10 faixas lineares do mín. ao máx. do ARQUIVO; ΔH contra a janela
  anterior > 1,5.)

Funções do z robusto, das faixas log e da JS vêm do próprio EntCusumZV3.py
(fonte única, usada também pelos gráficos).

Saídas: experiment_results/deteccao_pos_lb/resultados/T20_*.csv(.gz)
"""
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

OUT = "experiment_results/deteccao_pos_lb/resultados"
POS_T0 = np.arange(20, 141, 10)
K_GRADE = [3.5, 5, 7, 10, 15, 20, 30]
NB_GRADE = [10, 20]
FPR_MAX, TPR_MIN = 5.0, 95.0


from EntCusumZV3 import (bordas_log_baseline, divergencia_js, entropia_shannon as entropia,
                         histograma_faixas as hist, z_robusto_params)


def processa(args):
    run_id, path = args
    r = pd.read_csv(path).sort_values("timestamp")
    tt = (r.timestamp - r.timestamp.min()).values
    lac = np.diff(tt, prepend=tt[0])
    tt = tt - np.cumsum(np.where(lac > 2, lac, 0))
    v = r.rtt.values
    b = v[tt < 20]
    if len(b) < 10:
        return []
    med, mad = z_robusto_params(b)
    z = (v - med) / mad
    bordas = {nb: bordas_log_baseline(b, nb) for nb in NB_GRADE}
    pbase = {nb: hist(b, bordas[nb]) for nb in NB_GRADE}
    out = []
    for t0 in POS_T0:
        m = (tt >= t0) & (tt < t0 + 20)
        if m.sum() < 10:
            continue
        d = dict(run_id=run_id, t0=t0, n=int(m.sum()))
        for k in K_GRADE:
            d[f"fz_{k:g}"] = float((z[m] > k).mean())
        for nb in NB_GRADE:
            pw = hist(v[m], bordas[nb])
            d[f"dH_{nb}"] = abs(entropia(pw) - entropia(pbase[nb]))
            d[f"js_{nb}"] = divergencia_js(pw, pbase[nb])
        out.append(d)
    return out


def taxas(w, t, alarme, sub):
    det = alarme.groupby(w.run_id).any()
    tt = t[sub].set_index("run_id")
    d = det.reindex(tt.index).fillna(False)
    return {p: (int(d[tt[p]].sum()), int(tt[p].sum())) for p in ("NEG", "POS", "POS_D")}, d


def varrer(w, t, nome, valores, col):
    rows = []
    for v in valores:
        a = w[col] > v
        for parte, sub in (("selecao", t.sel), ("avaliacao", ~t.sel)):
            r, _ = taxas(w, t, a, sub)
            rows.append(dict(metodo=nome, valor=v, parte=parte, fpr=100 * r["NEG"][0] / r["NEG"][1],
                             tpr=100 * r["POS"][0] / r["POS"][1], tpr_dano=100 * r["POS_D"][0] / r["POS_D"][1]))
    return pd.DataFrame(rows)


def escolher(df):
    """(valor Youden, valor centro, lo, hi, existe_faixa)."""
    s = df[df.parte == "selecao"].sort_values("valor")
    ok = s[(s.fpr <= FPR_MAX) & (s.tpr_dano >= TPR_MIN)]
    if len(ok):
        lo, hi = ok.valor.min(), ok.valor.max()
        alvo = np.sqrt(lo * hi)
        centro = ok.valor.iloc[(np.log(ok.valor) - np.log(alvo)).abs().argsort().iloc[0]]
        youden = ok.assign(j=ok.tpr - ok.fpr).sort_values(["j", "valor"], ascending=[False, False]).valor.iloc[0]
        return youden, centro, lo, hi, True
    s = s.assign(j=s.tpr_dano - s.fpr)
    v = s.sort_values("j", ascending=False).valor.iloc[0]
    return v, v, np.nan, np.nan, False


if __name__ == "__main__":
    t = pd.read_csv(os.path.join(OUT, "execucoes_avaliadas.csv"))
    ok_int = (t.atk_ini.sub(20).abs() < 1) & (t.atk_fim.sub(160).abs() < 2)
    gil = t.gil.fillna(False).astype(bool)
    cap = t.captura.astype(bool)
    t["POS"] = t.ataque & ~gil & ok_int & ~cap
    t["POS_D"] = t.POS & t.escalou_no_ataque
    t["NEG"] = ~t.ataque & (t.normal_nom <= 640) & (t.normal_wu == 10) & ~cap
    t["sel"] = t.rep % 2 == 1
    t = t[t.POS | t.NEG].copy()
    t["faixa"] = pd.cut(t.normal_nom, [0, 25, 50, 100, 200, 350, 640],
                        labels=["16-25", "32-50", "64-100", "128-200", "210-350", "400-640"])

    with Pool(6) as p:
        W = pd.DataFrame([d for lst in p.map(processa, list(zip(t.run_id, t.rtt_path))) for d in lst])
    os.makedirs(OUT, exist_ok=True)
    W.to_csv(os.path.join(OUT, "T20_janelas_z_entropia.csv.gz"), index=False)

    fgrade = np.unique(np.round(np.logspace(-3.3, np.log10(0.6), 40), 5))
    todas, esc = [], []
    for k in K_GRADE:
        df = varrer(W, t, f"Z robusto k={k:g} (fração > f)", fgrade, f"fz_{k:g}")
        todas.append(df)
        v, c, lo, hi, ok = escolher(df)
        esc.append((f"Z robusto k={k:g} (fração > f)", f"fz_{k:g}", v, c, lo, hi, ok))
    for nb in NB_GRADE:
        for nome, col, grade in ((f"Entropia ΔH vs baseline, {nb} faixas log", f"dH_{nb}",
                                  np.unique(np.round(np.logspace(-2.5, np.log10(3), 40), 4))),
                                 (f"Entropia JS vs baseline, {nb} faixas log", f"js_{nb}",
                                  np.unique(np.round(np.logspace(-3.5, np.log10(0.9), 40), 5)))):
            df = varrer(W, t, nome, grade, col)
            todas.append(df)
            v, c, lo, hi, ok = escolher(df)
            esc.append((nome, col, v, c, lo, hi, ok))
    A = pd.concat(todas)
    A.to_csv(os.path.join(OUT, "T20a_varredura_z_entropia.csv"), index=False)

    ta = t[~t.sel].set_index("run_id")
    rows = []
    for nome, col, v_y, v_c, lo, hi, ok in esc:
      for criterio, v in (("Youden", v_y), ("centro", v_c)):
        a = W[col] > v
        det = a.groupby(W.run_id).any().reindex(ta.index).fillna(False)
        sel = A[(A.metodo == nome) & (A.valor == v) & (A.parte == "selecao")].iloc[0]
        d = dict(metodo=nome, criterio=criterio, limiar=v, faixa_aceitavel=f"{lo:g} – {hi:g}" if ok else "nenhuma",
                 sel_fpr=sel.fpr, sel_tpr=sel.tpr, sel_tpr_dano=sel.tpr_dano)
        for pop in ("NEG", "POS", "POS_D"):
            d[f"aval_{pop}"] = 100 * det[ta[pop]].mean()
        for f in ["16-25", "32-50", "64-100", "128-200", "210-350", "400-640"]:
            mm = ta.NEG & (ta.faixa == f)
            d[f"FPR_{f}"] = 100 * det[mm].mean() if mm.any() else np.nan
        rows.append(d)
    E = pd.DataFrame(rows)
    E.to_csv(os.path.join(OUT, "T20b_escolhidos_z_entropia.csv"), index=False)

    pd.set_option("display.width", 260)
    pd.set_option("display.max_rows", 500)
    print("populações: NEG", int(t.NEG.sum()), "POS", int(t.POS.sum()), "POS_D", int(t.POS_D.sum()),
          "| janelas:", len(W))
    print(E.round(2).to_string(index=False))
