"""
Análises ADICIONADAS ao plano (PLANO_DETECCAO_POS_LB.txt), motivadas pelos
primeiros resultados -- registradas como adição, não como desvio:

M10 Mecanismo da detecção. rtt_log mistura requisições normais e de ataque
    (sem rótulo por requisição). Cada requisição de ataque carrega WU de
    2e5-5e5 e é muito lenta. Pergunta: o piso de média (R1) dispara porque
    o tráfego LEGÍTIMO degrada (efeito colateral no servidor) ou só porque
    as próprias requisições de ataque, lentas, entram na média?
    Teste: em cada janela positiva, remove as k amostras mais lentas, com
    k = fração de requisições de ataque da execução (atk_req/(atk_req+
    normal_req)) x nº de amostras da janela -- "poda oráculo" que retira no
    máximo tantas amostras quantas o ataque pode ter gerado. Se a razão
    média/baseline volta para ~1, o sinal é o ataque em si; se continua alta,
    há degradação do tráfego legítimo. Reportado também com a mediana
    (estatística robusta, insensível a poucas amostras lentas).
M11 Viés de baseline. Em execuções SEM ataque, razão média_janela/baseline
    por posição -- se > 1 de forma sistemática, o baseline de t<20 s
    (aquecimento) subestima o regime estável, o que explicaria FPR alto do
    CUSUM (que acumula desvio em relação ao baseline).
"""
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

D = "experiment_results/deteccao_pos_lb"
OUT = os.path.join(D, "resultados")
POS = np.arange(20, 141, 10)


def analisa(args):
    rid, rtt_path, frac_atk, ataque = args
    df = pd.read_csv(rtt_path).sort_values("timestamp")
    t = (df["timestamp"] - df["timestamp"].min()).values
    v = df["rtt"].values
    base = v[t < 20]
    if len(base) < 10:
        return []
    bmean, bmed = base.mean(), np.median(base)
    out = []
    for t0 in POS:
        w = v[(t >= t0) & (t < t0 + 20)]
        if len(w) < 10:
            continue
        d = dict(run_id=rid, t0=t0, n=len(w), ratio_media=w.mean() / bmean, ratio_mediana=np.median(w) / bmed,
                 p95_base=np.percentile(base, 95))
        if ataque and frac_atk == frac_atk:
            k = int(np.ceil(frac_atk * len(w)))
            ws = np.sort(w)
            podada = ws[:len(ws) - k] if k < len(ws) else ws[:1]
            d["k_podadas"] = k
            d["ratio_media_podada"] = podada.mean() / bmean
            d["ratio_mediana_podada"] = np.median(podada) / bmed
            # quanto da elevação da média vem das k amostras mais lentas
            d["frac_elevacao_explicada"] = ((w.mean() - podada.mean()) / (w.mean() - bmean)
                                            if w.mean() > bmean else np.nan)
            # robustez: poda 50% a mais que o oráculo (remove também legítimas lentas
            # -> estimativa CONSERVADORA da degradação do tráfego legítimo)
            k2 = int(np.ceil(1.5 * frac_atk * len(w)))
            pod2 = ws[:len(ws) - k2] if k2 < len(ws) else ws[:1]
            d["ratio_media_podada15"] = pod2.mean() / bmean
            d["ratio_mediana_podada15"] = np.median(pod2) / bmed
        out.append(d)
    return out


def main():
    runs = pd.read_csv(os.path.join(D, "runs.csv"))
    t = pd.read_csv(os.path.join(OUT, "execucoes_avaliadas.csv"))
    t = t.set_index("run_id")
    runs["run_id"] = runs["familia"] + "/" + runs["suffix"]
    # fração de ataque DENTRO da janela de ataque (ataque dura 140 s, normal 180 s)
    runs["frac_atk"] = runs["atk_req"] / (runs["atk_req"] + runs["normal_req"] * 140 / 180)
    jobs = [(r.run_id, r.rtt_path, r.frac_atk, bool(r.ataque)) for r in runs.itertuples()]
    with Pool(10) as p:
        res = p.map(analisa, jobs, chunksize=8)
    w = pd.DataFrame([x for l in res for x in l])
    w.to_csv(os.path.join(D, "windows_mecanismo.csv.gz"), index=False, compression="gzip")

    # populações iguais às da análise principal
    ok = (t["atk_ini"].sub(20).abs() < 1) & (t["atk_fim"].sub(160).abs() < 2)
    gil = t["gil"].fillna(False).astype(bool)
    pos = t["ataque"] & ~gil & ok
    grupos = {
        "POS_D (ataque com dano)": pos & t["escalou_no_ataque"],
        "POS_ND (ataque sem dano)": pos & ~t["escalou_no_ataque"],
        "NEG (sem ataque, WU=10, <=640)": ~t["ataque"] & (t["normal_nom"] <= 640) & (t["normal_wu"] == 10),
    }
    rows = []
    for gn, m in grupos.items():
        ids = set(t.index[m])
        ww = w[w["run_id"].isin(ids)]
        # por execução: mediana das janelas positivas
        pr = ww.groupby("run_id").median(numeric_only=True)
        d = dict(grupo=gn, n_exec=len(pr))
        for c in ["ratio_media", "ratio_mediana", "ratio_media_podada", "ratio_mediana_podada", "ratio_media_podada15", "ratio_mediana_podada15",
                  "frac_elevacao_explicada", "k_podadas"]:
            if c in pr:
                q = pr[c].quantile([.25, .5, .75])
                d[c] = f"{q[.5]:.2f} [{q[.25]:.2f}-{q[.75]:.2f}]"
        for c, lim in [("ratio_media", 1.8), ("ratio_media_podada", 1.8), ("ratio_mediana", 1.8),
                       ("ratio_mediana_podada", 1.8), ("ratio_media_podada15", 1.8), ("ratio_mediana_podada15", 1.8)]:
            if c in ww:
                d[f"exec_com_janela_{c}>1.8_pct"] = round(100 * (ww.groupby("run_id")[c].max() > lim).mean(), 1)
        rows.append(d)
    m10 = pd.DataFrame(rows)
    m10.to_csv(os.path.join(OUT, "T13_mecanismo_poda_oraculo.csv"), index=False)
    print("=== M10 mecanismo (mediana por execução das janelas positivas; [P25-P75] entre execuções) ===")
    print(m10.T.to_string())

    # M10 por família x intensidade (só com dano e sem dano juntos)
    wp = w.merge(t[["familia", "pct", "escalou_no_ataque", "normal_nom"]], left_on="run_id", right_index=True)
    wp = wp[wp["run_id"].isin(set(t.index[pos]))]
    pr = wp.groupby("run_id").agg(fam=("familia", "first"), pct=("pct", "first"),
                                  dano=("escalou_no_ataque", "first"),
                                  r_media=("ratio_media", "max"), r_podada=("ratio_media_podada", "max"),
                                  r_mediana=("ratio_mediana", "max"))
    tab = pr.groupby(["fam", pr["pct"].fillna(-1), "dano"]).agg(
        n=("r_media", "size"),
        det_media=("r_media", lambda x: round(100 * (x > 1.8).mean(), 1)),
        det_podada=("r_podada", lambda x: round(100 * (x > 1.8).mean(), 1)),
        det_mediana=("r_mediana", lambda x: round(100 * (x > 1.8).mean(), 1)),
        r_podada_mediana=("r_podada", "median"), r_mediana_mediana=("r_mediana", "median"))
    tab.to_csv(os.path.join(OUT, "T13b_mecanismo_por_estrato.csv"))
    print("\n=== M10 por estrato: % de execuções com alguma janela acima de 1,8x (só o piso) ===")
    print(tab.round(2).to_string())

    # M11 viés de baseline nas negativas
    neg_ids = set(t.index[grupos["NEG (sem ataque, WU=10, <=640)"]])
    wn = w[w["run_id"].isin(neg_ids)].merge(t[["normal_nom"]], left_on="run_id", right_index=True)
    wn["faixa"] = pd.cut(wn["normal_nom"], [0, 50, 120, 250, 450, 700])
    m11 = wn.groupby(["faixa", "t0"], observed=True)["ratio_media"].median().unstack().round(2)
    m11.to_csv(os.path.join(OUT, "T14_vies_baseline_negativas.csv"))
    print("\n=== M11 negativas: mediana da razão média_janela/baseline por posição (t0) e faixa de carga ===")
    print(m11.to_string())
    geral = wn.groupby("run_id")["ratio_media"].median()
    print(f"\nNegativas: mediana (entre execuções) da razão típica = {geral.median():.3f}; "
          f"% execuções com razão típica > 1.05: {100*(geral>1.05).mean():.1f}%")


if __name__ == "__main__":
    main()
