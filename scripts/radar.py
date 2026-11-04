#!/usr/bin/env python3
"""Scanne un large univers PEA et écrit data/radar.json : tendance, signaux et plans chiffrés."""
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; no-risk-no-rari/1.0)"}
MISE = 200
FRAIS = 2


def historique(symbole, duree="2y"):
    code = urllib.parse.quote(symbole, safe="")
    erreur = None
    for essai in range(3):
        hote = "query1" if essai % 2 == 0 else "query2"
        url = f"https://{hote}.finance.yahoo.com/v8/finance/chart/{code}?range={duree}&interval=1d"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=ENTETES), timeout=20) as r:
                brut = json.load(r)["chart"]["result"][0]
            q = brut["indicators"]["quote"][0]
            lignes = [
                (t, o, h, b, c, v or 0)
                for t, o, h, b, c, v in zip(brut["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"])
                if None not in (o, h, b, c)
            ]
            return brut["meta"], lignes
        except Exception as exc:
            erreur = exc
            time.sleep(1 + essai * 2)
    raise RuntimeError(str(erreur))


def mm(valeurs, n, fin):
    return statistics.fmean(valeurs[fin - n + 1 : fin + 1]) if fin + 1 >= n else None


def rsi(c, fin, n=14):
    if fin < n:
        return None
    ecarts = [c[i] - c[i - 1] for i in range(fin - n + 1, fin + 1)]
    gains = sum(x for x in ecarts if x > 0)
    pertes = -sum(x for x in ecarts if x < 0)
    return 100.0 if pertes == 0 else 100 - 100 / (1 + gains / pertes)


def atr(h, b, c, fin, n=14):
    if fin < n:
        return None
    return statistics.fmean(
        max(h[i] - b[i], abs(h[i] - c[i - 1]), abs(b[i] - c[i - 1])) for i in range(fin - n + 1, fin + 1)
    )


def signaux(o, h, b, c, v, i):
    """Signaux connus à la clôture de la séance i, sans regarder le futur."""
    if i < 200:
        return None
    m20, m50, m200 = mm(c, 20, i), mm(c, 50, i), mm(c, 200, i)
    a, r = atr(h, b, c, i), rsi(c, i)
    vmoy = statistics.fmean(v[i - 20 : i]) or 0
    volrel = v[i] / vmoy if vmoy else None
    trouve = []
    haut20 = max(h[i - 20 : i])
    if c[i] > haut20 and c[i] > m50 and m50 > m200 and (volrel or 0) >= 1.5:
        trouve.append("Cassure")
    if c[i] > m200 and m50 > m200 and 38 <= r <= 52 and c[i] > c[i - 1] and c[i] <= m20 + a:
        trouve.append("Repli en tendance")
    if r < 30 and c[i] > m200:
        trouve.append("Survente")
    return {"m20": m20, "m50": m50, "m200": m200, "atr": a, "rsi": r, "volrel": volrel, "signaux": trouve, "haut20": haut20}


def plan(cours, a):
    risque = min(max(2 * a, 0), cours * 0.08)
    stop = cours - risque
    objectif = cours + 2 * risque
    qte = int(MISE // cours)
    return {
        "entree": round(cours, 3), "stop": round(stop, 3), "objectif": round(objectif, 3), "qte": qte,
        "montant": round(qte * cours, 2), "perte_max": round(qte * risque + FRAIS, 2),
        "gain_vise": round(qte * 2 * risque - FRAIS, 2),
    }


def main():
    univers = json.load(open("data/univers.json", encoding="utf-8"))
    symboles = [(s, "Action") for s in univers["actions"]] + [(s, "ETF") for s in univers["etf"]]
    try:
        _, cac = historique("^FCHI")
        cac_c = [l[4] for l in cac]
        cac20 = cac_c[-1] / cac_c[-21] - 1
    except Exception:
        cac20 = None
    lignes, erreurs = [], {}
    for code, genre in symboles:
        try:
            meta, l = historique(code + ".PA")
            _, o, h, b, c, v = (list(x) for x in zip(*l))
            i = len(c) - 1
            s = signaux(o, h, b, c, v, i)
            if not s:
                erreurs[code] = "historique trop court"
                continue
            capit = statistics.fmean(x * y for x, y in zip(c[-20:], v[-20:]))
            perf20 = c[i] / c[i - 20] - 1
            exclu = None
            if c[i] >= MISE:
                exclu = "part à plus de 200 €"
            elif c[i] < 1:
                exclu = "penny stock"
            elif genre == "Action" and capit < 500000:
                exclu = "peu liquide"
            tendance = "Haussière" if c[i] > s["m50"] > s["m200"] else "Baissière" if c[i] < s["m50"] < s["m200"] else "Neutre"
            score = len(s["signaux"]) * 3 + (2 if tendance == "Haussière" else -2 if tendance == "Baissière" else 0)
            if cac20 is not None:
                score += 1 if perf20 > cac20 else -1
            lignes.append({
                "symbole": code + ".PA", "nom": meta.get("shortName") or code, "type": genre,
                "cours": round(c[i], 3), "variation_pct": round((c[i] / c[i - 1] - 1) * 100, 2),
                "perf5_pct": round((c[i] / c[i - 5] - 1) * 100, 1), "perf20_pct": round(perf20 * 100, 1),
                "tendance": tendance, "rsi": round(s["rsi"], 1), "volume_relatif": round(s["volrel"], 2) if s["volrel"] else None,
                "mm20": round(s["m20"], 3), "mm50": round(s["m50"], 3), "mm200": round(s["m200"], 3),
                "atr14": round(s["atr"], 3), "signaux": s["signaux"], "score": score, "exclu": exclu,
                "plan": plan(c[i], s["atr"]) if s["signaux"] and not exclu else None,
            })
        except Exception as exc:
            erreurs[code] = str(exc)[:120]
        time.sleep(0.4)
    if len(lignes) < 20:
        print("Trop peu de valeurs, fichier conservé.", file=sys.stderr)
        return 1
    lignes.sort(key=lambda x: (-x["score"], -x["perf20_pct"]))
    with open("data/radar.json", "w", encoding="utf-8") as f:
        json.dump({"maj": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
                   "cac20_pct": round(cac20 * 100, 1) if cac20 is not None else None,
                   "valeurs": lignes, "erreurs": erreurs}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(len(lignes), "valeurs,", len(erreurs), "erreurs :", erreurs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
