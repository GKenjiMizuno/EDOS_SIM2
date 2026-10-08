"""
Calibração dos parâmetros dos detectores do EntCusumZV3 (changes.txt §129).
Só tabelas, sem Docker: usa as janelas já extraídas no §117
(experiment_results/deteccao_pos_lb/windows.csv.gz, 13 posições t0=20..140).

Populações (mesmas do §117): POS = execuções com ataque 20-160 s, sem S9-S11
(teto de GIL do gerador); POS_D = POS que escalaram no ataque (dano);
NEG = sem ataque, WU=10, carga normal <= 640 rps.
Protocolo: seleção nas repetições ÍMPARES, avaliação nas PARES (hold-out).
Unidade = execução (alarme se >= 1 das 13 janelas alarmar).

Critério do "ideal, nem grande nem pequeno": faixa aceitável F = valores com
FPR <= 5% E detecção de POS_D >= 95% na seleção; escolhido = centro de F em
escala log (máxima folga para os dois lados). Sem faixa aceitável -> relata o
melhor Youden (TPR_D - FPR) e diz que nenhum valor serve.

Saída: experiment_results/deteccao_pos_lb/resultados/T18_*.csv
"""
import os

import numpy as np
import pandas as pd

D = "experiment_results/deteccao_pos_lb"
OUT = os.path.join(D, "resultados")
POS_T0 = list(range(20, 141, 10))
FPR_MAX, TPR_MIN = 5.0, 95.0


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * p, 100 * max(0, c - m), 100 * min(1, c + m)


t = pd.read_csv(os.path.join(OUT, "execucoes_avaliadas.csv"))
w = pd.read_csv(os.path.join(D, "windows.csv.gz"))
w = w[w.avaliada.astype(bool) & w.t0.isin(POS_T0)].copy()

ok_int = (t.atk_ini.sub(20).abs() < 1) & (t.atk_fim.sub(160).abs() < 2)
gil = t.gil.fillna(False).astype(bool)
t["POS"] = t.ataque & ~gil & ok_int & ~t.captura.astype(bool)
t["POS_D"] = t.POS & t.escalou_no_ataque
t["NEG"] = ~t.ataque & (t.normal_nom <= 640) & (t.normal_wu == 10) & ~t.captura.astype(bool)
t["sel"] = t.rep % 2 == 1
t = t[t.POS | t.NEG].copy()
w = w[w.run_id.isin(t.run_id)].merge(t[["run_id", "POS", "POS_D", "NEG", "sel", "normal_nom"]], on="run_id")


def faixa(x):
    for lo, hi, nome in [(0, 25, "16-25"), (26, 50, "32-50"), (51, 100, "64-100"), (101, 200, "128-200"),
                         (201, 350, "210-350"), (351, 640, "400-640")]:
        if lo <= x <= hi:
            return nome


t["faixa"] = t.normal_nom.apply(faixa)


def taxas(alarm_win, sub):
    """alarm_win: Série booleana alinhada a w. Devolve dict de taxas por execução em `sub`."""
    det = alarm_win.groupby(w.run_id).any()
    tt = t[sub].set_index("run_id")
    d = det.reindex(tt.index).fillna(False)
    out = {}
    for pop in ("NEG", "POS", "POS_D"):
        m = tt[pop]
        out[pop] = (int(d[m].sum()), int(m.sum()))
    return out, d


def varrer(nome, valores, f_alarme):
    rows = []
    for v in valores:
        a = f_alarme(v)
        for parte, sub in (("selecao", t.sel), ("avaliacao", ~t.sel)):
            r, _ = taxas(a, sub)
            rows.append(dict(metodo=nome, valor=v, parte=parte,
                             fpr=100 * r["NEG"][0] / r["NEG"][1], tpr=100 * r["POS"][0] / r["POS"][1],
                             tpr_dano=100 * r["POS_D"][0] / r["POS_D"][1],
                             n_neg=r["NEG"][1], n_pos=r["POS"][1], n_dano=r["POS_D"][1]))
    return pd.DataFrame(rows)


def escolher(df, maior_e_mais_rigido=True):
    s = df[df.parte == "selecao"].sort_values("valor")
    ok = s[(s.fpr <= FPR_MAX) & (s.tpr_dano >= TPR_MIN)]
    if len(ok):
        lo, hi = ok.valor.min(), ok.valor.max()
        alvo = np.sqrt(lo * hi)
        v = ok.valor.iloc[(np.log(ok.valor) - np.log(alvo)).abs().argsort().iloc[0]]
        return v, lo, hi, True
    s = s.assign(j=s.tpr_dano - s.fpr)
    return s.sort_values("j", ascending=False).valor.iloc[0], np.nan, np.nan, False


# -------------------------------------------------- varreduras de 1 parâmetro
GRADES = {
    "CUSUM h (σ)": (np.unique(np.round(np.logspace(0, 5.5, 45), 1)), lambda v: w.cusum_sd > v),
    "Z-score limiar": ([3.5, 5, 7, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300], lambda v: w.max_z > v),
    "Entropia ΔH": ([0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5], lambda v: w.dH > v),
    "Média (x baseline)": (np.round(np.logspace(np.log10(1.05), np.log10(10), 40), 3), lambda v: w.ratio > v),
}
todas, escolhas = [], []
for nome, (vals, f) in GRADES.items():
    df = varrer(nome, vals, f)
    todas.append(df)
    v, lo, hi, ok = escolher(df)
    ev = df[(df.parte == "avaliacao") & (df.valor == v)].iloc[0]
    sl = df[(df.parte == "selecao") & (df.valor == v)].iloc[0]
    escolhas.append(dict(metodo=nome, escolhido=v, faixa_aceitavel=f"{lo:g} – {hi:g}" if ok else "nenhuma",
                         sel_fpr=sl.fpr, sel_tpr_dano=sl.tpr_dano,
                         aval_fpr=ev.fpr, aval_tpr=ev.tpr, aval_tpr_dano=ev.tpr_dano))

# -------------------------------------------------- combinado: média x CUSUM h (Z fixo 3,5, como no EntCusumZV3)
comb_rows = []
for r_ in [1.2, 1.3, 1.5, 1.8, 2.0, 2.5, 3.0]:
    for h_ in [5, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
        a = (w.ratio > r_) & ((w.max_z > 3.5) | (w.cusum_sd > h_))
        for parte, sub in (("selecao", t.sel), ("avaliacao", ~t.sel)):
            rr, _ = taxas(a, sub)
            comb_rows.append(dict(ratio=r_, h=h_, parte=parte, fpr=100 * rr["NEG"][0] / rr["NEG"][1],
                                  tpr=100 * rr["POS"][0] / rr["POS"][1], tpr_dano=100 * rr["POS_D"][0] / rr["POS_D"][1]))
comb = pd.DataFrame(comb_rows)
# combinado sem Z (média E CUSUM): mostra se o Z serve para alguma coisa
for r_ in [1.2, 1.3, 1.5, 1.8, 2.0, 2.5, 3.0]:
    for h_ in [5, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
        a = (w.ratio > r_) & (w.cusum_sd > h_)
        for parte, sub in (("selecao", t.sel), ("avaliacao", ~t.sel)):
            rr, _ = taxas(a, sub)
            comb_rows.append(dict(ratio=r_, h=h_, parte=parte + "_semZ", fpr=100 * rr["NEG"][0] / rr["NEG"][1],
                                  tpr=100 * rr["POS"][0] / rr["POS"][1], tpr_dano=100 * rr["POS_D"][0] / rr["POS_D"][1]))
comb = pd.DataFrame(comb_rows)

os.makedirs(OUT, exist_ok=True)
pd.concat(todas).to_csv(os.path.join(OUT, "T18a_varredura_1_parametro.csv"), index=False)
esc = pd.DataFrame(escolhas)
esc.to_csv(os.path.join(OUT, "T18b_parametros_escolhidos.csv"), index=False)
comb.to_csv(os.path.join(OUT, "T18c_varredura_combinado.csv"), index=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
print("populações: NEG", int(t.NEG.sum()), "| POS", int(t.POS.sum()), "| POS_D", int(t.POS_D.sum()),
      "| seleção (reps ímpares):", int(t.sel.sum()), "| avaliação (pares):", int((~t.sel).sum()))
print("\n=== varreduras (seleção) ===")
a = pd.concat(todas)
print(a[a.parte == "selecao"].round(1).to_string(index=False))
print("\n=== escolhidos (avaliados nas reps pares) ===")
print(esc.round(1).to_string(index=False))
print("\n=== combinado (seleção) ===")
for parte in ("selecao", "selecao_semZ"):
    c = comb[comb.parte == parte]
    print(parte, "FPR")
    print(c.pivot(index="ratio", columns="h", values="fpr").round(1).to_string())
    print(parte, "TPR dano")
    print(c.pivot(index="ratio", columns="h", values="tpr_dano").round(1).to_string())
    print(parte, "TPR todos")
    print(c.pivot(index="ratio", columns="h", values="tpr").round(1).to_string())


# -------------------------------------------------- candidatos: avaliação detalhada (reps pares)
# 1º SCALE_UP de cada execução com dano (relógio da simulação) e 1º alarme
# (fim da 1ª janela que alarma, relógio do rtt_log -- conservador: o log
# corre à frente pelos saltos do WSL2, §128, então o alarme parece mais tarde).
def primeiro_su(path):
    m = pd.read_csv(path)
    s = m[(m.decision == "SCALE_UP") & (m.elapsed_time_s > 20)].elapsed_time_s
    return s.min() if len(s) else np.nan


t.loc[t.POS_D, "t_su"] = [primeiro_su(p) for p in t.loc[t.POS_D, "metrics_path"]]
CANDIDATOS = [
    ("CUSUM h=5σ (padrão antigo)", w.cusum_sd > 5),
    ("CUSUM h=1000σ", w.cusum_sd > 1000),
    ("CUSUM h=2000σ", w.cusum_sd > 2000),
    ("CUSUM h=5000σ", w.cusum_sd > 5000),
    ("CUSUM h=18000σ (centro da faixa)", w.cusum_sd > 17782.8),
    ("Média > 1,3x", w.ratio > 1.3),
    ("Média > 1,5x", w.ratio > 1.5),
    ("Média > 1,8x (padrão)", w.ratio > 1.8),
    ("Média > 3,5x (centro da faixa)", w.ratio > 3.5),
    ("Combinado padrão (1,8x E (Z>3,5 OU CUSUM>5σ))", (w.ratio > 1.8) & ((w.max_z > 3.5) | (w.cusum_sd > 5))),
    ("Média > 1,5x E CUSUM > 2000σ", (w.ratio > 1.5) & (w.cusum_sd > 2000)),
    ("Z > 30", w.max_z > 30),
    ("Entropia ΔH > 0,2", w.dH > 0.2),
]
FAIXAS = ["16-25", "32-50", "64-100", "128-200", "210-350", "400-640"]
cand = []
aval = ~t.sel
ta = t[aval].set_index("run_id")
for nome, a in CANDIDATOS:
    det = a.groupby(w.run_id).any().reindex(ta.index).fillna(False)
    prim = (w[a].groupby("run_id").t0.min() + 20).reindex(ta.index)
    d = dict(regra=nome)
    for pop in ("NEG", "POS", "POS_D"):
        k, n = int(det[ta[pop]].sum()), int(ta[pop].sum())
        p, lo, hi = wilson(k, n)
        d[pop] = f"{p:.1f}% [{lo:.0f}-{hi:.0f}] (n={n})"
    dd = ta[ta.POS_D]
    antes = (prim[dd.index] <= dd.t_su).sum()
    d["alarme_antes_1o_SCALE_UP"] = f"{100 * antes / len(dd):.0f}%"
    d["1o_alarme_mediano_s"] = prim[ta.POS].median()
    for f in FAIXAS:
        m = ta.NEG & (ta.faixa == f)
        d[f"FPR_{f}"] = round(100 * det[m].mean(), 1) if m.any() else np.nan
    cand.append(d)
cand = pd.DataFrame(cand)
cand.to_csv(os.path.join(OUT, "T18d_candidatos_avaliacao.csv"), index=False)
print("\n=== candidatos nas reps PARES (avaliação) ===")
print(cand.drop(columns=[c for c in cand if c.startswith("FPR_")]).to_string(index=False))
print(cand[["regra"] + [c for c in cand if c.startswith("FPR_")]].to_string(index=False))
print("n NEG por faixa (avaliação):", ta[ta.NEG].faixa.value_counts().reindex(FAIXAS).to_dict())

# o que escapa: ataques NÃO detectados pelo candidato principal
a = (w.cusum_sd > 2000)
det = a.groupby(w.run_id).any().reindex(t.set_index("run_id").index).fillna(False)
esc_ = t.set_index("run_id")[t.set_index("run_id").POS & ~det]
print("\n=== ataques não detectados por CUSUM 2000σ (todas as reps) ===")
print(esc_.groupby(["familia", "cenario", "pct", "atk_wu"]).size().to_string())
print("deles, com dano:", int(esc_.POS_D.sum()), "| max_inst:", esc_.max_inst.value_counts().to_dict())
