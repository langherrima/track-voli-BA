"""
Monitoraggio open-jaw Milano -> Buenos Aires (20-24/12) + Santiago -> Milano (8-11/1).
Gira lun-mar-mer-gio. 20 combinazioni di date; ogni esecuzione ne controlla COMBO_GIORNO
a rotazione (1 credito SerpApi ciascuna): due esecuzioni consecutive coprono tutte le 20.
Budget piano free, mese peggiore (19 giorni lun-gio): 13 x 19 = 247 <= 250.
Scrive ALERT_SCL.md (il workflow apre una issue) se:
  - il minimo del giorno e' un nuovo minimo storico e <= SOGLIA_SCL, oppure
  - una combinazione cala di almeno CALO_PCT rispetto alla sua ultima rilevazione.
"""
import os, csv, json, datetime as dt, requests

API_KEY      = os.environ["SERPAPI_KEY"]
SOGLIA       = int(os.environ.get("SOGLIA_SCL", 1450))
CALO_PCT     = float(os.environ.get("CALO_PCT", 10))
COMBO_GIORNO = int(os.environ.get("COMBO_GIORNO", 13))
MILANO       = "MXP,LIN,BGY"
ANDATE       = [dt.date(2026, 12, g) for g in range(20, 25)]
RITORNI      = [dt.date(2027, 1, g) for g in range(8, 12)]
COMBO        = [(a, r) for a in ANDATE for r in RITORNI]
CSV_FILE     = "storico_bue_scl.csv"
COLONNE      = ["data", "andata", "ritorno", "prezzo", "compagnie_andata",
                "scali_andata", "durata_andata_h", "partenza"]

oggi = dt.date.today()
if oggi >= ANDATE[0]:
    raise SystemExit("Prima data di partenza raggiunta: monitoraggio concluso.")

if oggi.weekday() > 3:
    raise SystemExit("Oggi non e' tra lunedi' e giovedi': nessuna ricerca.")

# rotazione sul numero di esecuzioni lun-gio (non sui giorni di calendario)
settimane, resto = divmod((oggi - dt.date(2026, 10, 5)).days, 7)   # 5/10/2026 = lunedi'
esecuzione = settimane * 4 + resto
start = (esecuzione * COMBO_GIORNO) % len(COMBO)
da_controllare = [COMBO[(start + i) % len(COMBO)] for i in range(COMBO_GIORNO)]

storico = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        storico = [{c: r.get(c, "") for c in COLONNE} for r in csv.DictReader(f)]
prev_min = min((int(r["prezzo"]) for r in storico if r["prezzo"]), default=None)
ultimo = {(r["andata"], r["ritorno"]): int(r["prezzo"]) for r in storico if r["prezzo"]}

nuove, avvisi = [], []
for andata, ritorno in da_controllare:
    tratte = [{"departure_id": MILANO, "arrival_id": "EZE", "date": andata.isoformat()},
              {"departure_id": "SCL", "arrival_id": MILANO, "date": ritorno.isoformat()}]
    try:
        d = requests.get("https://serpapi.com/search", params={
            "engine": "google_flights", "type": 3, "multi_city_json": json.dumps(tratte),
            "stops": 3, "currency": "EUR", "hl": "it", "gl": "it", "api_key": API_KEY,
        }, timeout=60).json()
    except requests.RequestException as e:
        print(f"{andata} / {ritorno}: errore di rete ({e})"); continue
    if "error" in d:
        print(f"{andata} / {ritorno}: errore SerpApi ({d['error']})"); continue
    voli = [v for v in d.get("best_flights", []) + d.get("other_flights", []) if "price" in v]
    if not voli:
        print(f"{andata} / {ritorno}: nessun volo"); continue

    best = min(voli, key=lambda v: v["price"])
    riga = {
        "data": oggi.isoformat(), "andata": andata.isoformat(), "ritorno": ritorno.isoformat(),
        "prezzo": best["price"],
        "compagnie_andata": " + ".join(sorted({f["airline"] for f in best["flights"]})),
        "scali_andata": len(best["flights"]) - 1,
        "durata_andata_h": round(best.get("total_duration", 0) / 60, 1),
        "partenza": best["flights"][0]["departure_airport"]["id"],
    }
    nuove.append(riga)
    print(f"{andata} / {ritorno}: {riga['prezzo']} EUR ({riga['compagnie_andata']}, "
          f"{riga['scali_andata']} scali andata, {riga['durata_andata_h']} h, da {riga['partenza']})")

    prec = ultimo.get((riga["andata"], riga["ritorno"]))
    if prec:
        calo = (prec - best["price"]) / prec * 100
        if calo >= CALO_PCT:
            avvisi.append(f"- {andata} / {ritorno}: {best['price']} EUR, calo del {calo:.1f}% (era {prec} EUR)")

if not nuove:
    raise SystemExit("Nessun prezzo ottenuto oggi.")

storico += nuove
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLONNE)
    w.writeheader(); w.writerows(storico)

m = min(nuove, key=lambda r: r["prezzo"])
if m["prezzo"] <= SOGLIA and (prev_min is None or m["prezzo"] < prev_min):
    avvisi.insert(0, f"Nuovo minimo storico: {m['prezzo']} EUR - andata {m['andata']}, ritorno {m['ritorno']}, "
                     f"{m['compagnie_andata']}, partenza da {m['partenza']} (precedente: {prev_min} EUR, soglia {SOGLIA} EUR).")

if avvisi:
    with open("ALERT_SCL.md", "w", encoding="utf-8") as f:
        f.write("Milano -> Buenos Aires / Santiago -> Milano\n\n" + "\n".join(avvisi))
