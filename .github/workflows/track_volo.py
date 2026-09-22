"""
Monitoraggio giornaliero volo Milano -> Buenos Aires (1 credito SerpApi per esecuzione).
Registra il prezzo A/R minimo con andata AR 1141 (via FCO) e il minimo assoluto del giorno.
Se il prezzo scende sotto SOGLIA ed e' un nuovo minimo, scrive ALERT.md (il workflow apre una issue).
"""
import os, csv, datetime as dt, requests

API_KEY  = os.environ["SERPAPI_KEY"]
SOGLIA   = int(os.environ.get("SOGLIA", 1450))
ANDATA   = dt.date(2026, 12, 21)
RITORNO  = dt.date(2027, 1, 12)
VOLO     = "AR 1141"
CSV_FILE = "storico_prezzi.csv"

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
target = [v for v in voli if any(f.get("flight_number") == VOLO for f in v["flights"])]
p_target = min((v["price"] for v in target), default=None)
p_min = min((v["price"] for v in voli), default=None)
livello = d.get("price_insights", {}).get("price_level", "")

storico = list(csv.DictReader(open(CSV_FILE))) if os.path.exists(CSV_FILE) else []
prev_min = min((int(r["prezzo_volo"]) for r in storico if r["prezzo_volo"]), default=None)

nuovo = not os.path.exists(CSV_FILE)
with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if nuovo:
        w.writerow(["data", "prezzo_volo", "prezzo_min_giorno", "livello_google"])
    w.writerow([oggi.isoformat(), p_target or "", p_min or "", livello])
print(f"{oggi}: {VOLO} = {p_target} EUR | minimo giorno = {p_min} EUR | {livello}")

if p_target is None:
    open("ALERT.md", "w").write(f"Il volo {VOLO} non compare nei risultati del {oggi}. Minimo del giorno: {p_min} EUR.")
elif p_target <= SOGLIA and (prev_min is None or p_target < prev_min):
    open("ALERT.md", "w").write(
        f"Prezzo sceso a {p_target} EUR (soglia {SOGLIA} EUR, minimo precedente {prev_min} EUR).\n\n"
        f"Andata {ANDATA} {VOLO} via FCO, ritorno {RITORNO}. Livello Google: {livello}.")
