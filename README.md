# Opstellingen-agent · Bet-Experts.nl

Genereert automatisch **opstellingen-artikelen** (Eredivisie + Keuken Kampioen Divisie)
in de Webflow Nieuws-collectie, op basis van de Bet-Experts API-proxy (Cloudflare Worker).

- **Avond ervóór** (`generate.py`): maakt per wedstrijd een *"Vermoedelijke opstelling …"*-artikel
  (verwachte XI uit de laatste wedstrijden, blessures, vorm, H2H, AI-model-kansen, FAQ) en publiceert het.
  → hele nacht indexeringstijd, 's ochtends al op Google.
- **Wedstrijddag** (`finalize.py`): zodra de echte opstelling binnen is (~1u voor aftrap) wordt hetzelfde
  artikel bijgewerkt naar *"Definitieve opstelling …"* (zelfde slug/URL, dus geen her-indexering nodig).

## Belangrijk
- **Geen wedtips** — de winkansen komen expliciet van een *AI-model*, niet van Bet-Experts.
- **Geen tabellen** (Webflow rich-text ondersteunt die niet): alles is koppen + alinea's + lijsten.
- Content wordt gesplitst over **content / content-2 / content-3**; SEO-meta staat in **samenvatting**.
- De **slug blijft gelijk** bij het flippen naar definitief, zodat URL's/links niet breken.

## Draaien
```bash
export WEBFLOW_TOKEN="..."           # Webflow site-token (CMS read+write)

python3 generate.py --date 2026-09-12 --preview   # HTML-previews, schrijft niks
python3 generate.py --date 2026-09-12 --dry       # alleen tellen
python3 generate.py --date 2026-09-12             # live aanmaken + publiceren
python3 finalize.py --dry                         # kijk wat er geflipt zou worden
python3 finalize.py                               # live flippen naar definitief
python3 cleanup.py --dry                          # welke oude artikelen zouden weg?
python3 cleanup.py                                # verwijder oude + schrijf redirects
```
Zonder `--date` pakt `generate.py` **morgen** (Europe/Amsterdam).

## GitHub Actions
- `generate.yml` — cron 18:00 UTC (≈20:00 NL), maakt de artikelen voor de volgende dag.
- `finalize.yml` — cron elke 30 min 08:00-20:00 UTC, flipt naar definitief zodra de opstelling er is.
- `cleanup.yml` — dagelijks 05:30 UTC, verwijdert opstellingen ouder dan `RETENTION_DAYS` na de
  wedstrijd en schrijft 301-redirects (oude URL → `/opstellingen`) naar `redirects/opstellingen-redirects.csv`.
  **Voeg die redirects toe in Webflow → Publishing** (SEO-veilig, geen 404's).
- Secret nodig: **`WEBFLOW_TOKEN`** (Settings → Secrets and variables → Actions).
- De workflows committen `state/opstellingen.json` (+ redirects) terug (koppeling fixture-id → CMS-item).

## Hub
Elk artikel linkt naar de hub **`/opstellingen`** (in te stellen via `HUB_PATH` in `oa_config.py`).
Bouw die hub als Collection List op de Nieuws-collectie, **gefilterd op rubriek = Opstellingen**,
gesorteerd op wedstrijddatum.

## Competities
Aan te passen in `oa_config.py → LEAGUES`. Nu: Eredivisie + Keuken Kampioen Divisie (`eerste-divisie`).
Nieuwe competitie toevoegen = één regel (worker-slug + competitiepagina-slug + naam).

## Bestanden
| Bestand | Functie |
|---|---|
| `oa_config.py` | competities, Webflow-ids, data-mappings |
| `oa_api.py` | calls naar de Bet-Experts API-proxy |
| `oa_match.py` | verzamelt alle data per wedstrijd + bouwt Webflow-velddata |
| `oa_build.py` | schrijft titel, samenvatting en de 3 content-delen (toon van de voorbeschouwingen) |
| `oa_webflow.py` | Webflow aanmaken/updaten/publiceren + state |
| `generate.py` / `finalize.py` | de twee cron-scripts |
| `data/` | team-id→slug en club/competitie-slug-mappings |
