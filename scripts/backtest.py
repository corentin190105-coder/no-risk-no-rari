#!/usr/bin/env python3
"""Teste les signaux de radar.py sur 5 ans et les compare à des entrées sans signal."""
import json
import random
import statistics
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from radar import atr, historique, signaux

MISE, FRAIS = 200, 2
FRAIS_PCT = FRAIS / MISE * 100
HORIZON = 10


def trade(o, h, b, c, i, a):
    """Entrée à l'ouverture de i+1, stop à 2 ATR (8 % max), objectif 2 fois le risque, 10 séances max."""
    e = o[i + 1]
    risque = min(2 * a, e * 0.08)
    stop, obj = e - risque, e + 2 * risque
    fin = min(i + HORIZON, len(c) - 1)
    for j in range(i + 1, fin + 1):
        if o[j] <= stop:
            return (o[j] / e - 1) * 100
        if b[j] <= stop:
            return (stop / e - 1) * 100
        if o[j] >= obj or h[j] >= obj:
            return (max(o[j], obj) / e - 1) * 100
    return (c[fin] / e - 1) * 100


def bilan(perfs):
    if not perfs:
        return {"n": 0}
    nets = [p - FRAIS_PCT for p in perfs]
    return {
        "n": len(nets), "gagnants_pct": round(sum(x > 0 for x in nets) / len(nets) * 100, 1),
        "moyenne_nette_pct": round(statistics.fmean(nets), 2), "mediane_nette_pct": round(statistics.median(nets), 2),
        "moyenne_brute_pct": round(statistics.fmean(perfs), 2),
    }


def main():
    u = json.load(open("data/univers.json", encoding="utf-8"))
    res, tout, erreurs = {}, [], []
    random.seed(7)
    for code in u["actions"]:
        try:
            _, l = historique(code + ".PA", "5y")
            t, o, h, b, c, v = (list(x) for x in zip(*l))
            for i in range(200, len(c) - HORIZON - 1):
                s = signaux(o, h, b, c, v, i)
                if not s or c[i] >= MISE or c[i] < 1:
                    continue
                p = trade(o, h, b, c, i, s["atr"])
                for nom in s["signaux"]:
                    res.setdefault(nom, []).append((t[i], p))
                if random.random() < 0.05:
                    res.setdefault("Sans signal (hasard)", []).append((t[i], p))
                tout.append(t[i])
        except Exception:
            erreurs.append(code)
        time.sleep(0.4)
    if not tout:
        return 1
    coupure = sorted(tout)[int(len(tout) * 0.6)]
    sortie = {"maj": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
              "regle": "Entrée à l'ouverture suivante, stop à 2 ATR (8 % maximum), objectif à 2 fois le risque, 10 séances maximum, 2 € de frais sur 200 €.",
              "limite": "Univers actuel seulement, donc sans les sociétés disparues : les résultats sont flattés. Performances passées, sans garantie.",
              "valeurs_exclues": erreurs, "resultats": {}}
    for nom, l in res.items():
        sortie["resultats"][nom] = {
            "total": bilan([p for _, p in l]),
            "periode_ancienne": bilan([p for t, p in l if t < coupure]),
            "periode_recente": bilan([p for t, p in l if t >= coupure]),
        }
    with open("data/backtest.json", "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(sortie["resultats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
