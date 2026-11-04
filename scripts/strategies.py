#!/usr/bin/env python3
"""Compare des méthodes à plus long horizon à un panier égal de l'univers, sur 5 ans."""
import json
import statistics
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from radar import historique

LIGNE = 200  # euros par ligne, 1 € par ordre
NB = 5


def stats(rets, par_an):
    if not rets:
        return {"n": 0}
    v, pic, dd = 1.0, 1.0, 0.0
    for r in rets:
        v *= 1 + r
        pic = max(pic, v)
        dd = min(dd, v / pic - 1)
    return {"n": len(rets), "annuel_pct": round((v ** (par_an / len(rets)) - 1) * 100, 1), "pire_baisse_pct": round(dd * 100, 1)}


def portefeuille(px, dates, choix):
    rets, avant = [], set()
    for k in range(0, len(dates) - 1):
        d0, d1 = dates[k], dates[k + 1]
        sel = choix(d0)
        if not sel:
            rets.append(0.0)
            avant = set()
            continue
        brut = statistics.fmean(px[s][d1] / px[s][d0] - 1 for s in sel if d1 in px[s] and d0 in px[s])
        ordres = len(set(sel) - avant) + len(avant - set(sel))
        rets.append(brut - ordres * 1 / (LIGNE * len(sel)))
        avant = set(sel)
    return rets


def main():
    u = json.load(open("data/univers.json", encoding="utf-8"))
    px, ohlc = {}, {}
    for code in u["actions"]:
        try:
            _, l = historique(code + ".PA", "5y")
            px[code] = {x[0] // 86400: x[4] for x in l}
            ohlc[code] = l
        except Exception:
            pass
        time.sleep(0.4)
    _, cac = historique("^FCHI", "5y")
    jours = [x[0] // 86400 for x in cac]
    cac_p = {x[0] // 86400: x[4] for x in cac}
    pas = 21
    idx = list(range(260, len(jours), pas))
    dates = [jours[i] for i in idx]
    pos = {d: i for i, d in zip(idx, dates)}

    def perf(s, d, loin, pres):
        i = pos[d]
        a, b = jours[i - loin], jours[i - pres]
        return px[s][b] / px[s][a] - 1 if a in px[s] and b in px[s] else None

    def eligibles(d):
        return [s for s in px if d in px[s] and px[s][d] < 200]

    def mm200(s, d):
        i = pos[d]
        v = [px[s][j] for j in jours[i - 200 : i] if j in px[s]]
        return statistics.fmean(v) if len(v) > 150 else None

    def momentum(d, loin=252, filtre=False):
        c = []
        for s in eligibles(d):
            p = perf(s, d, loin, 21)
            if p is None:
                continue
            if filtre and not (mm200(s, d) and px[s][d] > mm200(s, d)):
                continue
            c.append((p, s))
        return [s for _, s in sorted(c, reverse=True)[:NB]]

    def calme(d):
        c = []
        i = pos[d]
        for s in eligibles(d):
            v = [px[s].get(j) for j in jours[i - 120 : i]]
            v = [x for x in v if x]
            if len(v) > 100:
                c.append((statistics.pstdev(b / a - 1 for a, b in zip(v, v[1:])), s))
        return [s for _, s in sorted(c)[:NB]]

    res = {
        "Panier égal de toutes les actions": portefeuille(px, dates, lambda d: eligibles(d)),
        "Momentum 12 mois, 5 lignes": portefeuille(px, dates, momentum),
        "Momentum 6 mois au-dessus de la MM200": portefeuille(px, dates, lambda d: momentum(d, 126, True)),
        "5 actions les moins volatiles": portefeuille(px, dates, calme),
    }
    # le panier égal sert de repère : sans frais
    res["Panier égal de toutes les actions"] = [
        statistics.fmean(px[s][dates[k + 1]] / px[s][dates[k]] - 1 for s in eligibles(dates[k]) if dates[k + 1] in px[s])
        for k in range(len(dates) - 1)
    ]
    res["CAC 40 (hors dividendes)"] = [cac_p[dates[k + 1]] / cac_p[dates[k]] - 1 for k in range(len(dates) - 1)]
    coupe = len(dates) // 2
    sortie = {"maj": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
              "regle": "Revue tous les 21 jours de bourse, 200 € par ligne, 1 € par ordre, hors dividendes et hors fiscalité.",
              "methodes": {k: {"total": stats(v, 12), "ancien": stats(v[:coupe], 12), "recent": stats(v[coupe:], 12)} for k, v in res.items()}}
    # gap sur nouvelle : proxy d'une annonce positive, conservation 20 séances
    gaps, gaps_t, tous = [], [], []
    for s, l in ohlc.items():
        for i in range(200, len(l) - 21):
            vm = statistics.fmean(x[5] for x in l[i - 20 : i]) or 1
            base = (l[i + 21][4] / l[i + 1][1] - 1) * 100 - 1
            if i % 40 == 0:
                tous.append(base)
            if l[i][4] / l[i - 1][4] - 1 >= 0.05 and l[i][5] >= 2 * vm and l[i][4] >= l[i][2] - (l[i][2] - l[i][3]) * 0.3 and l[i][4] < 200:
                gaps.append(base)
                if l[i][4] > statistics.fmean(x[4] for x in l[i - 200 : i]):
                    gaps_t.append(base)
    b = lambda v: {"n": len(v), "moyenne_nette_pct": round(statistics.fmean(v), 2), "gagnants_pct": round(sum(x > 0 for x in v) / len(v) * 100, 1)} if v else {"n": 0}
    sortie["evenements"] = {"Hausse de 5 % sur fort volume, 20 séances": b(gaps), "Idem au-dessus de la MM200": b(gaps_t), "Entrée au hasard, 20 séances": b(tous)}
    with open("data/strategies.json", "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(sortie, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
