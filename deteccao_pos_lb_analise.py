"""
Análise da reavaliação da detecção estatística pós load balancer
(PLANO_DETECCAO_POS_LB.txt -- métricas M1-M9, hipóteses H1-H4, Q1-Q5).
Lê o que deteccao_pos_lb_extract.py salvou e grava só TABELAS (sem
gráficos, a pedido) em experiment_results/deteccao_pos_lb/resultados/.
"""
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

D = "experiment_results/deteccao_pos_lb"
OUT = os.path.join(D, "resultados")
os.makedirs(OUT, exist_ok=True)
SEED = 20260930
B = 2000
DEFAULT = dict(z=3.5, ratio=1.8, h=5.0, dh=1.5)
REGRAS = ["R1_combinada", "R2_z", "R3_cusum", "R4_entropia", "R5_z_ou_cusum"]
ATK0, ATK1 = 20.0, 160.0
rng = np.random.default_rng(SEED)
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)


# ---------------------------------------------------------------------------
# utilidades estatísticas
# ---------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * p, 100 * max(0, c - half), 100 * min(1, c + half))


def boot_ratio(k, n, reps=B):
    """IC por conglomerado: reamostra execuções, estatística = soma(k)/soma(n)."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    if n.sum() == 0:
        return (np.nan, np.nan, np.nan)
    idx = rng.integers(0, len(k), size=(reps, len(k)))
    r = k[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return (100 * k.sum() / n.sum(), 100 * np.percentile(r, 2.5), 100 * np.percentile(r, 97.5))


def fmt(t):
    return f"{t[0]:.1f} [{t[1]:.1f}-{t[2]:.1f}]" if t[0] == t[0] else "-"


# ---------------------------------------------------------------------------
# carga e janelas avaliadas
# ---------------------------------------------------------------------------
def carregar(tag=""):
    runs = pd.read_csv(os.path.join(D, f"runs{tag}.csv"))
    win = pd.read_csv(os.path.join(D, f"windows{tag}.csv.gz"))
    runs["run_id"] = runs["familia"] + "/" + runs["suffix"]
    return runs, win


def posicoes(w):
    """Posições t0 com [t0, t0+w) inteiramente dentro de [20,160] (mesmas p/ negativas)."""
    stride = w / 2
    ts = np.arange(0, 200, stride)
    return ts[(ts >= ATK0 - 1e-6) & (ts + w <= ATK1 + 1e-6)]


def alarmes(win, z, ratio, h, dh):
    ev = win["avaliada"].astype(bool)
    az = ev & (win["max_z"] > z)
    ac = ev & (win["cusum_sd"] > h)
    return {
        "R1_combinada": ev & (win["ratio"] > ratio) & (az | ac),
        "R2_z": az,
        "R3_cusum": ac,
        "R4_entropia": ev & (win["dH"] > dh),
        "R5_z_ou_cusum": az | ac,
        "_piso": ev & (win["ratio"] > ratio),
    }


def por_execucao(runs, win, w=20, z=DEFAULT["z"], ratio=DEFAULT["ratio"], h=DEFAULT["h"], dh=DEFAULT["dh"]):
    """Tabela 1 linha/execução: nº de posições, avaliadas, alarmes por regra."""
    pos = posicoes(w)
    ww = win[win["t0"].round(3).isin(np.round(pos, 3))].copy()
    al = alarmes(ww, z, ratio, h, dh)
    for r in REGRAS:
        ww[r] = al[r].astype(int)
    ww["avaliada_i"] = ww["avaliada"].astype(int)
    g = ww.groupby("run_id").agg(n_aval=("avaliada_i", "sum"), **{f"k_{r}": (r, "sum") for r in REGRAS})
    out = runs.set_index("run_id").join(g, how="left")
    out["n_pos"] = len(pos)
    out[["n_aval"] + [f"k_{r}" for r in REGRAS]] = out[["n_aval"] + [f"k_{r}" for r in REGRAS]].fillna(0)
    for r in REGRAS:
        out[f"det_{r}"] = out[f"k_{r}"] > 0
    return out.reset_index()


def populacoes(t):
    ok_int = (t["atk_ini"].sub(ATK0).abs() < 1) & (t["atk_fim"].sub(ATK1).abs() < 2)
    gil = t.get("gil", pd.Series(False, index=t.index)).fillna(False).astype(bool)
    pos = t["ataque"] & ~gil & ok_int
    neg = ~t["ataque"] & (t["normal_nom"] <= 640) & (t["normal_wu"] == 10)
    return {
        "POS (ataque, principal)": pos,
        "POS_D (ataque com dano)": pos & t["escalou_no_ataque"],
        "POS_ND (ataque sem dano)": pos & ~t["escalou_no_ataque"],
        "NEG (sem ataque, WU=10, <=640)": neg,
        "NEG_ALL (todas sem ataque)": ~t["ataque"],
        "GIL (S9-S11, separado)": t["ataque"] & gil,
    }


# ---------------------------------------------------------------------------
# análises
# ---------------------------------------------------------------------------
def tabela_ponto_operacao(t, nome="T1_ponto_operacao"):
    pops = populacoes(t)
    linhas = []
    for pn, m in pops.items():
        s = t[m]
        for r in REGRAS:
            linhas.append(dict(
                populacao=pn, regra=r, n_exec=len(s),
                janela_pct=fmt(boot_ratio(s[f"k_{r}"], s["n_pos"])),
                execucao_pct=fmt(wilson(int(s[f"det_{r}"].sum()), len(s))),
            ))
    df = pd.DataFrame(linhas)
    df.to_csv(os.path.join(OUT, f"{nome}.csv"), index=False)
    return df


def tabela_estratos(t):
    pops = populacoes(t)
    s = t[pops["POS (ataque, principal)"]].copy()
    s["intens"] = s["pct"].fillna(-1)
    keys = ["familia", "cenario", "normal_nom", "intens", "atk_wu", "atacantes", "rps_atacante"]
    for k in keys:
        if k not in s:
            s[k] = np.nan
    g = s.groupby(keys, dropna=False)
    rows = []
    for key, gg in g:
        d = dict(zip(keys, key))
        d["n"] = len(gg)
        d["n_dano"] = int(gg["escalou_no_ataque"].sum())
        for r in ["R1_combinada", "R2_z", "R3_cusum"]:
            d[f"det_exec_{r}"] = round(100 * gg[f"det_{r}"].mean(), 1)
            d[f"det_janela_{r}"] = round(100 * gg[f"k_{r}"].sum() / gg["n_pos"].sum(), 1)
        d["furtivos_R1"] = int((gg["escalou_no_ataque"] & ~gg["det_R1_combinada"]).sum())
        d["work_ratio_med"] = gg["work_ratio"].median()
        d["atk_err_med"] = gg["atk_err"].median()
        rows.append(d)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T2_estratos_positivos.csv"), index=False)
    return df


def tabela_furtividade(t):
    pops = populacoes(t)
    s = t[pops["POS_D (ataque com dano)"]]
    rows = []
    for r in REGRAS:
        k = int((~s[f"det_{r}"]).sum())
        rows.append(dict(estrato="TODOS", regra=r, n_dano=len(s), furtivos=k, pct=fmt(wilson(k, len(s)))))
    for (fam, pct), gg in s.groupby(["familia", s["pct"].fillna(-1)]):
        for r in ["R1_combinada", "R2_z", "R3_cusum"]:
            k = int((~gg[f"det_{r}"]).sum())
            rows.append(dict(estrato=f"{fam} | intens={pct:g}%", regra=r, n_dano=len(gg), furtivos=k,
                             pct=fmt(wilson(k, len(gg)))))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T3_furtividade.csv"), index=False)
    lista = s[~s["det_R1_combinada"]][["familia", "suffix", "normal_nom", "pct", "atk_wu", "atacantes",
                                       "work_ratio", "n_scale_up", "k_R2_z", "k_R3_cusum", "base_mean"]]
    lista.to_csv(os.path.join(OUT, "T3b_execucoes_furtivas_R1.csv"), index=False)
    return df, lista


def tabela_latencia(t, win, w=20):
    pops = populacoes(t)
    s = t[pops["POS (ataque, principal)"]]
    ww = win[win["run_id"].isin(s["run_id"]) & (win["t0"] >= ATK0 - w / 2 - 1e-6) & (win["t0"] + w <= ATK1 + 1e-6)].copy()
    al = alarmes(ww, **DEFAULT)
    rows = []
    for r in REGRAS:
        x = ww[al[r].values].groupby("run_id")["t0"].min()
        lat = (x + w) - ATK0
        q = lat.quantile([.25, .5, .75]) if len(lat) else pd.Series([np.nan] * 3, index=[.25, .5, .75])
        rows.append(dict(regra=r, n_detectadas=len(lat), lat_p25=q[.25], lat_mediana=q[.5], lat_p75=q[.75],
                         pct_ate_30s=round(100 * (lat <= 30).mean(), 1) if len(lat) else np.nan))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T4_latencia.csv"), index=False)
    return df


def tabela_cobertura(t):
    pops = populacoes(t)
    rows = []
    for pn in ["POS (ataque, principal)", "POS_D (ataque com dano)", "NEG (sem ataque, WU=10, <=640)",
               "GIL (S9-S11, separado)"]:
        s = t[pops[pn]]
        perd = s["n_pos"] - s["n_aval"]
        rows.append(dict(populacao=pn, n_exec=len(s),
                         janelas_perdidas_pct=fmt(boot_ratio(perd, s["n_pos"])),
                         exec_com_perda_pct=round(100 * (perd > 0).mean(), 1),
                         erros_ataque_mediana=s["atk_err"].median(), erros_normal_mediana=s["normal_err"].median()))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T5_cobertura.csv"), index=False)
    return df


def faixa_carga(x):
    return pd.cut(x, [0, 50, 120, 250, 450, 700, 1e9],
                  labels=["<=50", "51-120", "121-250", "251-450", "451-700", ">700"])


def tabela_fpr_estratos(t):
    s = t[~t["ataque"]].copy()
    s["faixa"] = faixa_carga(s["normal_nom"])
    rows = []
    for keys, gg in s.groupby(["familia", "faixa", "normal_wu", "escalou"], observed=True):
        d = dict(zip(["familia", "faixa_carga", "normal_wu", "escalou"], keys))
        d["n"] = len(gg)
        for r in REGRAS:
            d[f"fpr_exec_{r}"] = round(100 * gg[f"det_{r}"].mean(), 1)
        rows.append(d)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T6_fpr_estratos.csv"), index=False)
    return df


def scores(t, win, w=20):
    pos = posicoes(w)
    ww = win[win["t0"].round(3).isin(np.round(pos, 3)) & win["avaliada"].astype(bool)].copy()
    ww["margem_R1"] = np.minimum(ww["ratio"] / DEFAULT["ratio"],
                                 np.maximum(ww["max_z"] / DEFAULT["z"], ww["cusum_sd"] / DEFAULT["h"]))
    g = ww.groupby("run_id").agg(s_ratio=("ratio", "max"), s_z=("max_z", "max"), s_cusum=("cusum_sd", "max"),
                                 s_dH=("dH", "max"), s_margem_R1=("margem_R1", "max"))
    out = t.set_index("run_id").join(g, how="left").reset_index()
    fill = dict(s_ratio=1.0, s_z=0.0, s_cusum=0.0, s_dH=0.0, s_margem_R1=0.0)  # sem janela avaliada = sem evidência
    return out.fillna(fill)


def auc_ci(y, s, reps=1000):
    y, s = np.asarray(y), np.asarray(s)
    if len(set(y)) < 2:
        return (np.nan, np.nan, np.nan)
    a = roc_auc_score(y, s)
    p, n = np.where(y == 1)[0], np.where(y == 0)[0]
    bs = []
    for _ in range(reps):
        ii = np.concatenate([rng.choice(p, len(p)), rng.choice(n, len(n))])
        bs.append(roc_auc_score(y[ii], s[ii]))
    return (a, np.percentile(bs, 2.5), np.percentile(bs, 97.5))


def tabela_auc(ts):
    pops = populacoes(ts)
    neg = ts[pops["NEG (sem ataque, WU=10, <=640)"]]
    rows = []
    for alvo in ["POS_D (ataque com dano)", "POS (ataque, principal)"]:
        pos = ts[pops[alvo]]
        estratos = [("todas as cargas", pos, neg)]
        for lo, hi in [(0, 50), (51, 120), (121, 250), (251, 450)]:
            estratos.append((f"carga normal {lo}-{hi}", pos[pos.normal_nom.between(lo, hi)],
                             neg[neg.normal_nom.between(lo, hi)]))
        for en, p, n in estratos:
            y = np.r_[np.ones(len(p)), np.zeros(len(n))]
            for sc in ["s_ratio", "s_z", "s_cusum", "s_dH", "s_margem_R1"]:
                a = auc_ci(y, np.r_[p[sc].values, n[sc].values])
                rows.append(dict(positivos=alvo, estrato=en, n_pos=len(p), n_neg=len(n), score=sc,
                                 auc=round(a[0], 3), ic95=f"{a[1]:.3f}-{a[2]:.3f}"))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T7_auc.csv"), index=False)
    return df


def tabela_neyman_pearson(t, win, alvo_fpr=5.0):
    """Seleção em repetições ímpares, avaliação em pares (hold-out)."""
    impar = t["rep"] % 2 == 1
    pops = populacoes(t)
    # Grade ampliada (desvio registrado: a 1ª versão ia só até piso 3.0, z 8,
    # h 12 -- Z/CUSUM/"Z ou CUSUM" não chegavam a FPR <= alvo dentro dela).
    grade = [(r, z, h) for r in np.round(np.r_[np.arange(1.1, 3.0, 0.1), np.arange(3.0, 8.01, 0.5)], 2)
             for z in np.r_[np.arange(2.0, 10.0, 1.0), np.arange(10.0, 80.1, 5.0)]
             for h in np.r_[np.arange(2.0, 20.0, 2.0), np.arange(20.0, 200.1, 10.0)]]
    pos_p = posicoes(20)
    ww = win[win["t0"].round(3).isin(np.round(pos_p, 3))]
    ev = ww["avaliada"].astype(bool).values
    rid = ww["run_id"].values
    ratio, mz, cs = ww["ratio"].values, ww["max_z"].values, ww["cusum_sd"].values
    runs_idx = {r: i for i, r in enumerate(t["run_id"])}
    ridx = np.array([runs_idx.get(r, -1) for r in rid])
    ok = ridx >= 0

    def det_runs(mask):
        d = np.zeros(len(t), bool)
        np.logical_or.at(d, ridx[ok & mask], True)
        return d

    negI = (pops["NEG (sem ataque, WU=10, <=640)"] & impar).values
    negP = (pops["NEG (sem ataque, WU=10, <=640)"] & ~impar).values
    posDI = (pops["POS_D (ataque com dano)"] & impar).values
    posDP = (pops["POS_D (ataque com dano)"] & ~impar).values
    posP = (pops["POS (ataque, principal)"] & ~impar).values
    baixa = (t["pct"].fillna(100) <= 5).values
    rows = []
    familias_regra = {
        "R1_combinada": lambda r, z, h: ev & (ratio > r) & ((mz > z) | (cs > h)),
        "R2_z": lambda r, z, h: ev & (mz > z),
        "R3_cusum": lambda r, z, h: ev & (cs > h),
        "piso_sozinho": lambda r, z, h: ev & (ratio > r),
        "R5_z_ou_cusum": lambda r, z, h: ev & ((mz > z) | (cs > h)),
    }
    for nome, f in familias_regra.items():
        melhor = None
        vistos = set()
        for (r, z, h) in grade:
            chave = (r if "R1" in nome or "piso" in nome else 0, z if nome in ("R1_combinada", "R2_z", "R5_z_ou_cusum") else 0,
                     h if nome in ("R1_combinada", "R3_cusum", "R5_z_ou_cusum") else 0)
            if chave in vistos:
                continue
            vistos.add(chave)
            d = det_runs(f(*chave))
            fpr = 100 * d[negI].mean()
            if fpr > alvo_fpr:
                continue
            tpr = 100 * d[posDI].mean()
            if melhor is None or tpr > melhor[0] + 1e-9:
                melhor = (tpr, fpr, chave, d)
        if melhor is None:
            continue
        tprI, fprI, chave, d = melhor
        rows.append(dict(
            regra=nome, alvo_fpr=alvo_fpr, piso=chave[0] or "-", z=chave[1] or "-", h_sigma=chave[2] or "-",
            sel_TPR_dano_impar=round(tprI, 1), sel_FPR_impar=round(fprI, 1),
            holdout_TPR_dano=fmt(wilson(int(d[posDP].sum()), int(posDP.sum()))),
            holdout_TPR_dano_intens_ate5=fmt(wilson(int(d[posDP & baixa].sum()), int((posDP & baixa).sum()))),
            holdout_TPR_todos_ataques=fmt(wilson(int(d[posP].sum()), int(posP.sum()))),
            holdout_FPR=fmt(wilson(int(d[negP].sum()), int(negP.sum()))),
            n_neg_holdout=int(negP.sum()), n_dano_holdout=int(posDP.sum()),
        ))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, f"T8_neyman_pearson_fpr{alvo_fpr:g}.csv"), index=False)
    return df


def tabela_logistica(t):
    pops = populacoes(t)
    s = t[pops["POS (ataque, principal)"]].copy()
    s = s[(s["work_ratio"] > 0) & (s["vol_ratio"] > 0) & (s["normal_rps_real"] > 0)]
    s["lw"] = np.log10(s["work_ratio"])
    s["lv"] = np.log10(s["vol_ratio"])
    s["ln"] = np.log10(s["normal_rps_real"])
    modelos = {"volume": ["lv"], "trabalho": ["lw"], "trabalho+carga": ["lw", "ln"],
               "volume+carga": ["lv", "ln"], "completo": ["lw", "lv", "ln"]}
    rows, coefs = [], []
    for alvo in ["det_R1_combinada", "det_R2_z", "det_R3_cusum"]:
        y = s[alvo].astype(int).values
        if y.min() == y.max():
            continue
        gkf = GroupKFold(n_splits=5)
        for mn, cols in modelos.items():
            X = s[cols].values
            aucs, lls = [], []
            for tr, te in gkf.split(X, y, groups=s["config"]):
                if len(set(y[tr])) < 2 or len(set(y[te])) < 2:
                    continue
                m = LogisticRegression(penalty=None, max_iter=2000).fit(X[tr], y[tr])
                p = m.predict_proba(X[te])[:, 1]
                aucs.append(roc_auc_score(y[te], p))
                lls.append(log_loss(y[te], p, labels=[0, 1]))
            rows.append(dict(alvo=alvo, modelo=mn, auc_cv=round(np.mean(aucs), 3),
                             logloss_cv=round(np.mean(lls), 3), n=len(s), taxa_det=round(100 * y.mean(), 1)))
        cols = ["lw", "ln"]
        m = LogisticRegression(penalty=None, max_iter=2000).fit(s[cols].values, y)
        grupos = [np.where(s["config"].values == c)[0] for c in s["config"].unique()]
        Xall = s[cols].values
        bs = []
        for _ in range(500):
            ii = np.concatenate([grupos[j] for j in rng.integers(0, len(grupos), len(grupos))])
            yy = y[ii]
            if yy.min() == yy.max():
                continue
            bs.append(LogisticRegression(penalty=None, max_iter=2000).fit(Xall[ii], yy).coef_[0])
        bs = np.array(bs)
        for i, c in enumerate(cols):
            coefs.append(dict(alvo=alvo, variavel={"lw": "log10 razão de trabalho", "ln": "log10 rps normal real"}[c],
                              coef=round(m.coef_[0][i], 3),
                              ic95=f"{np.percentile(bs[:, i], 2.5):.3f} a {np.percentile(bs[:, i], 97.5):.3f}",
                              odds_ratio_por_10x=round(float(np.exp(m.coef_[0][i])), 2)))
    df, dc = pd.DataFrame(rows), pd.DataFrame(coefs)
    df.to_csv(os.path.join(OUT, "T9a_logistica_comparacao_modelos.csv"), index=False)
    dc.to_csv(os.path.join(OUT, "T9b_logistica_coeficientes.csv"), index=False)
    # Faixas em escala log (desvio registrado no relatório: a 1ª versão usava
    # faixas 0.1-30, mas a razão de trabalho real vai de ~10^2 a ~10^5 porque
    # WU_ataque/WU_normal = 2e4-5e4).
    s["faixa_trabalho"] = pd.cut(s["lw"], [0, 2.5, 3, 3.5, 4, 4.5, 9],
                                 labels=["<316", "316-1k", "1k-3.2k", "3.2k-10k", "10k-32k", ">32k"])
    bins = s.groupby("faixa_trabalho", observed=True).agg(
        n=("lw", "size"), det_R1=("det_R1_combinada", "mean"), det_R2=("det_R2_z", "mean"),
        det_R3=("det_R3_cusum", "mean"), dano=("escalou_no_ataque", "mean")).mul(
        [1, 100, 100, 100, 100]).round(1)
    bins.to_csv(os.path.join(OUT, "T9c_deteccao_por_razao_trabalho.csv"))
    return df, dc, bins


def tabela_sensibilidade(t, win):
    pops = populacoes(t)
    rows = []
    varre = {"ratio": np.round(np.arange(1.2, 3.01, 0.2), 1), "z": np.arange(2, 6.01, 0.5),
             "h": np.arange(2, 10.01, 1)}
    for par, vals in varre.items():
        for v in vals:
            p = dict(DEFAULT)
            p[par] = v
            tt = por_execucao(t.drop(columns=[c for c in t.columns if c.startswith(("k_", "det_", "n_aval", "n_pos"))]),
                              win, **p)
            for r in ["R1_combinada", "R2_z", "R3_cusum"]:
                rows.append(dict(parametro=par, valor=v, regra=r,
                                 tpr_exec_dano=round(100 * tt.loc[pops["POS_D (ataque com dano)"].values, f"det_{r}"].mean(), 1),
                                 tpr_exec_todos=round(100 * tt.loc[pops["POS (ataque, principal)"].values, f"det_{r}"].mean(), 1),
                                 fpr_exec=round(100 * tt.loc[pops["NEG (sem ataque, WU=10, <=640)"].values, f"det_{r}"].mean(), 1)))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "T10a_sensibilidade_limiares.csv"), index=False)
    return df


def prep(runs):
    runs = runs.copy()
    runs["vol_ratio"] = runs["atk_rps_real"] / runs["normal_rps_real"]
    runs["work_ratio"] = (runs["atk_rps_real"] * runs["atk_wu"]) / (runs["normal_rps_real"] * runs["normal_wu"])
    return runs


def main():
    runs, win = carregar()
    runs = prep(runs)
    t = por_execucao(runs, win)
    pops = populacoes(t)
    print("Tamanhos:", {k: int(v.sum()) for k, v in pops.items()})
    excl = t[t["ataque"] & ~((t["atk_ini"].sub(ATK0).abs() < 1) & (t["atk_fim"].sub(ATK1).abs() < 2))]
    print("Excluídas por intervalo de ataque atípico:", excl["run_id"].tolist())

    print("\n=== T1 ponto de operação original (z=3.5, piso 1.8x, h=5σ, ΔH=1.5) ===")
    print(tabela_ponto_operacao(t).to_string(index=False))
    print("\n=== T3 furtividade (dano sem alarme) ===")
    f, lista = tabela_furtividade(t)
    print(f[f.estrato == "TODOS"].to_string(index=False))
    print(f[(f.estrato != "TODOS") & (f.regra == "R1_combinada")].to_string(index=False))
    print("\n=== T4 latência ===")
    print(tabela_latencia(t, win).to_string(index=False))
    print("\n=== T5 cobertura ===")
    print(tabela_cobertura(t).to_string(index=False))
    print("\n=== T6 FPR estratos (negativas) ===")
    print(tabela_fpr_estratos(t).to_string(index=False))
    e = tabela_estratos(t)
    print("\n=== T2 (resumo): detecção por execução por família x intensidade ===")
    s = t[pops["POS (ataque, principal)"]]
    print(s.groupby(["familia", s["pct"].fillna(-1)]).agg(
        n=("run_id", "size"), dano=("escalou_no_ataque", "sum"),
        R1=("det_R1_combinada", "mean"), R2=("det_R2_z", "mean"), R3=("det_R3_cusum", "mean"),
        R4=("det_R4_entropia", "mean")).round(3).to_string())
    print("\n=== T7 AUC (independente de limiar) ===")
    ts = scores(t, win)
    a = tabela_auc(ts)
    print(a.to_string(index=False))
    print("\n=== T8 Neyman-Pearson hold-out ===")
    for alvo in [5.0, 1.0]:
        print(tabela_neyman_pearson(t, win, alvo).to_string(index=False))
    print("\n=== T9 logística ===")
    df, dc, bins = tabela_logistica(t)
    print(df.to_string(index=False)); print(dc.to_string(index=False)); print(bins.to_string())
    print("\n=== T10 sensibilidade de limiares ===")
    sens = tabela_sensibilidade(runs, win)
    print(sens.to_string(index=False))
    print("\n=== T10b sensibilidade ao tamanho de janela (ponto de operação original) ===")
    rows = []
    for w, tag in [(10, "_w10"), (20, ""), (30, "_w30")]:
        rr, ww = carregar(tag)
        tt = por_execucao(prep(rr), ww, w=w)
        pp = populacoes(tt)
        for r in ["R1_combinada", "R2_z", "R3_cusum"]:
            rows.append(dict(janela_s=w, regra=r,
                             tpr_exec_dano=round(100 * tt.loc[pp["POS_D (ataque com dano)"], f"det_{r}"].mean(), 1),
                             tpr_janela_todos=round(100 * tt.loc[pp["POS (ataque, principal)"], f"k_{r}"].sum() /
                                                   tt.loc[pp["POS (ataque, principal)"], "n_pos"].sum(), 1),
                             fpr_exec=round(100 * tt.loc[pp["NEG (sem ataque, WU=10, <=640)"], f"det_{r}"].mean(), 1)))
    wdf = pd.DataFrame(rows)
    wdf.to_csv(os.path.join(OUT, "T10b_sensibilidade_janela.csv"), index=False)
    print(wdf.to_string(index=False))
    print("\n=== T11 grupo GIL (S9-S11) ===")
    g = t[pops["GIL (S9-S11, separado)"]]
    gg = g.groupby(["cenario", "pct"]).agg(n=("run_id", "size"), dano=("escalou_no_ataque", "mean"),
                                          R1=("det_R1_combinada", "mean"), R2=("det_R2_z", "mean"),
                                          base_rtt=("base_mean", "median")).round(2)
    gg.to_csv(os.path.join(OUT, "T11_grupo_gil.csv"))
    print(gg.to_string())
    t.to_csv(os.path.join(OUT, "execucoes_avaliadas.csv"), index=False)

    # ---------------- Q5 antigo x novo ----------------
    print("\n=== T12 antigo x novo ===")
    ro, wo = carregar("_prefix")
    ro = prep(ro)
    to = por_execucao(ro, wo)
    po = populacoes(to)
    # (A) experimento natural dentro do wedos_grid pré-correção: mesma era de código, captura on x off
    w = to[po["POS (ataque, principal)"] & (to["familia"] == "wedos_grid")].copy()
    cfg_on = set(w[w["captura"]]["config"]); cfg_off = set(w[~w["captura"]]["config"])
    comuns = cfg_on & cfg_off
    w = w[w["config"].isin(comuns)]
    A = w.groupby("captura").agg(n=("run_id", "size"), configs=("config", "nunique"),
                                 rtt_base_mediana=("base_mean", "median"), rtt_base_dp_mediana=("base_std", "median"),
                                 dano=("escalou_no_ataque", "mean"),
                                 R1=("det_R1_combinada", "mean"), R2=("det_R2_z", "mean"),
                                 R3=("det_R3_cusum", "mean"))
    # pareado por configuração: diferença de taxa de detecção on-off
    pares = w.groupby(["config", "captura"])[["det_R1_combinada", "det_R2_z", "det_R3_cusum"]].mean().unstack()
    difs = {}
    for r in ["det_R1_combinada", "det_R2_z", "det_R3_cusum"]:
        dd = (pares[(r, True)] - pares[(r, False)]).dropna().values
        bs = [rng.choice(dd, len(dd)).mean() for _ in range(B)]
        difs[r] = f"{100*dd.mean():.1f} pp [{100*np.percentile(bs,2.5):.1f} a {100*np.percentile(bs,97.5):.1f}] (n_cfg={len(dd)})"
    print("(A) wedos_grid pré-correção, configs com as duas condições:")
    print(A.round(3).to_string())
    print("Diferença pareada por config (captura ON - OFF):", difs)
    A.to_csv(os.path.join(OUT, "T12a_captura_on_off_wedos_prefix.csv"))
    pd.Series(difs).to_csv(os.path.join(OUT, "T12a_diferenca_pareada.csv"))
    # (B) dataset antigo x novo, mesma métrica, por família
    rows = []
    for nome, tt, pp in [("ANTIGO (pré-correção)", to, po), ("NOVO (pós-correção)", t, pops)]:
        for fam in ["wedos_grid", "combined_sweep", "atacantes_intensidade_grid", "desempate_combinado_isolado",
                    "clients_rps_grid", "normal_baseline"]:
            for pn in ["POS (ataque, principal)", "POS_D (ataque com dano)", "NEG (sem ataque, WU=10, <=640)"]:
                sub = tt[pp[pn] & (tt["familia"] == fam)]
                if not len(sub):
                    continue
                d = dict(dataset=nome, familia=fam, populacao=pn, n=len(sub),
                         captura_pct=round(100 * sub["captura"].mean(), 0),
                         rtt_base_mediana=round(sub["base_mean"].median(), 2))
                for r in REGRAS:
                    d[r] = round(100 * sub[f"det_{r}"].mean(), 1)
                rows.append(d)
    Bdf = pd.DataFrame(rows)
    Bdf.to_csv(os.path.join(OUT, "T12b_antigo_vs_novo.csv"), index=False)
    print(Bdf.to_string(index=False))


if __name__ == "__main__":
    main()
