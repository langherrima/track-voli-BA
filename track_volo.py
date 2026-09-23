"""
Monitoraggio giornaliero volo Milano -> Buenos Aires (1 credito SerpApi per esecuzione).
Registra il prezzo A/R minimo con andata AR 1141 (via FCO), il minimo assoluto del giorno
e i dettagli dell'itinerario piu' economico del giorno.
Se il prezzo scende sotto SOGLIA ed e' un nuovo minimo, scrive ALERT.md (il workflow apre una issue).
"""
import os, csv, datetime as dt, requests

API_KEY  = os.environ["SERPAPI_KEY"]
SOGLIA   = int(os.environ.get("SOGLIA", 1450))
ANDATA   = dt.date(2026, 12, 21)
RITORNO  = dt.date(2027, 1, 12)
VOLO     = "AR 1141"
CSV_FILE = "storico_prezzi.csv"
COLONNE  = ["data", "prezzo_volo", "prezzo_min_giorno", "livello_google",
            "min_compagnie", "min_scali", "min_durata_h", "min_partenza"]

oggi = dt.date.today()
if oggi >= ANDATA:
    raise SystemExit("Data di partenza raggiunta: monitoraggio concluso.")

d = requests.get("https://serpapi.com/search", params={
    "engine": "google_flights", "departure_id": "MXP,LIN,BGY", "arrival_id": "EZE",
    "outbound_date": ANDATA.isoformat(), "return_date": RITORNO.isoformat(),
    "type": 1, "stops": 3, "currency": "EUR", "hl": "it", "gl": "it", "api_key": API_KEY,
}, timeout=60).json()
if "error" in d:
    raise SystemExit("Errore SerpApi: " + d["error"])

voli = [v for v in d.get("best_flights", []) + d.get("other_flights", []) if "price" in v]
if not voli:
    raise SystemExit("Nessun volo restituito per queste date.")
target = [v for v in voli if any(f.get("flight_number") == VOLO for f in v["flights"])]
p_target = min((v["price"] for v in target), default=None)
best = min(voli, key=lambda x: x["price"])
livello = d.get("price_insights", {}).get("price_level", "")

riga = {
    "data": oggi.isoformat(), "prezzo_volo": p_target or "",
    "prezzo_min_giorno": best["price"], "livello_google": livello,
    "min_compagnie": " + ".join(sorted({f["airline"] for f in best["flights"]})),
    "min_scali": len(best["flights"]) - 1,
    "min_durata_h": round(best.get("total_duration", 0) / 60, 1),
    "min_partenza": best["flights"][0]["departure_airport"]["id"],
}

# rilegge lo storico e lo riallinea alle colonne attuali (i vecchi campi mancanti restano vuoti)
storico = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        storico = [{c: r.get(c, "") for c in COLONNE} for r in csv.DictReader(f)]
prev_min = min((int(r["prezzo_volo"]) for r in storico if r["prezzo_volo"]), default=None)
storico.append(riga)

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLONNE)
    w.writeheader(); w.writerows(storico)

print(f"{oggi}: {VOLO} = {p_target} EUR | minimo giorno = {riga['prezzo_min_giorno']} EUR "
      f"({riga['min_compagnie']}, {riga['min_scali']} scali, {riga['min_durata_h']} h, da {riga['min_partenza']}) | {livello}")

if p_target is None:
    open("ALERT.md", "w").write(f"Il volo {VOLO} non compare nei risultati del {oggi}. Minimo del giorno: {riga['prezzo_min_giorno']} EUR.")
elif p_target <= SOGLIA and (prev_min is None or p_target < prev_min):
    open("ALERT.md", "w").write(
        f"Prezzo sceso a {p_target} EUR (soglia {SOGLIA} EUR, minimo precedente {prev_min} EUR).\n\n"
        f"Andata {ANDATA} {VOLO} via FCO, ritorno {RITORNO}. Livello Google: {livello}.\n\n"
        f"Minimo del giorno: {riga['prezzo_min_giorno']} EUR - {riga['min_compagnie']}, "
        f"{riga['min_scali']} scali, {riga['min_durata_h']} h, da {riga['min_partenza']}.")
