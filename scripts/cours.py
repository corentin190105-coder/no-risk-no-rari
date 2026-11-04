#!/usr/bin/env python3
"""Récupère cours, volumes et indicateurs pour data/suivi.json et écrit data/cours.json."""
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HOTES = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; no-risk-no-rari/1.0)"}


def telecharge(symbole):
    code = urllib.parse.quote(symbole, safe="")
    erreur = None
    for tentative in range(3):
        hote = HOTES[tentative % 2]
        url = f"https://{hote}/v8/finance/chart/{code}?range=6mo&interval=1d"
        try:
            requete = urllib.request.Request(url, headers=ENTETES)
            with urllib.request.urlopen(requete, timeout=20) as reponse:
                return json.load(reponse)["chart"]["result"][0]
        except Exception as exc:
            erreur = exc
            time.sleep(2 + tentative * 3)
    raise RuntimeError(f"{symbole}: {erreur}")


def moyenne(valeurs, n):
    return round(statistics.fmean(valeurs[-n:]), 4) if len(valeurs) >= n else None


def atr(hauts, bas, clotures, n=14):
    if len(clotures) < n + 1:
        return None
    etendues = [
        max(h - b, abs(h - c), abs(b - c))
        for h, b, c in zip(hauts[1:], bas[1:], clotures[:-1])
    ]
    return round(statistics.fmean(etendues[-n:]), 4)


def analyse(symbole):
    brut = telecharge(symbole)
    meta = brut["meta"]
    q = brut["indicators"]["quote"][0]
    barres = [
        (t, h, b, c, v or 0)
        for t, h, b, c, v in zip(
            brut["timestamp"], q["high"], q["low"], q["close"], q["volume"]
        )
        if None not in (h, b, c)
    ]
    if len(barres) < 2:
        raise RuntimeError(f"{symbole}: historique insuffisant")
    dates, hauts, bas, clotures, volumes = (list(x) for x in zip(*barres))
    zone = ZoneInfo(meta.get("exchangeTimezoneName", "Europe/Paris"))
    date_barre = datetime.fromtimestamp(dates[-1], zone).date()
    instant = meta.get("regularMarketTime", dates[-1])
    date_cours = datetime.fromtimestamp(instant, zone).date()
    cours = meta.get("regularMarketPrice", clotures[-1])
    # Sans barre du jour, la dernière barre est la clôture de référence.
    if date_barre == date_cours:
        veille = clotures[-2]
        haut, bas_jour, volume = hauts[-1], bas[-1], volumes[-1]
    else:
        veille = clotures[-1]
        haut, bas_jour, volume = None, None, None
    volumes_passes = [v for v in volumes[-21:-1] if v]
    return {
        "nom": meta.get("shortName") or meta.get("longName"),
        "devise": meta.get("currency"),
        "cours": round(cours, 4),
        "veille": round(veille, 4),
        "variation_pct": round((cours / veille - 1) * 100, 2),
        "plus_haut": haut,
        "plus_bas": bas_jour,
        "volume": volume,
        "volume_moyen_20j": round(statistics.fmean(volumes_passes)) if volumes_passes else None,
        "mm20": moyenne(clotures, 20),
        "mm50": moyenne(clotures, 50),
        "atr14": atr(hauts, bas, clotures),
        "plus_haut_6m": round(max(hauts), 4),
        "plus_bas_6m": round(min(bas), 4),
        "heure_cours": datetime.fromtimestamp(instant, timezone.utc).isoformat(),
    }


def main():
    suivi = json.load(open("data/suivi.json", encoding="utf-8"))
    symboles = suivi["valeurs"] + suivi["indices"]
    resultats, erreurs = {}, {}
    for symbole in symboles:
        try:
            resultats[symbole] = analyse(symbole)
        except Exception as exc:
            erreurs[symbole] = str(exc)[:200]
            print("ERREUR", erreurs[symbole], file=sys.stderr)
        time.sleep(1)
    if not resultats:
        print("Aucun cours récupéré, fichier conservé.", file=sys.stderr)
        return 1
    sortie = {
        "maj": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
        "source": "Yahoo Finance, non officielle, cours parfois différés",
        "cours": resultats,
        "erreurs": erreurs,
    }
    with open("data/cours.json", "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(resultats)} cours, {len(erreurs)} erreurs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
