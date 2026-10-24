# -*- coding: utf-8 -*-
"""Verwijdert oude opstellingen-artikelen (ouder dan RETENTION_DAYS na de wedstrijd)
om onder de Webflow CMS-limiet te blijven — SEO-veilig: schrijft per verwijderd
artikel een 301-redirectregel (oude URL -> hub) weg die je in Webflow toevoegt.

  python3 cleanup.py --dry     # laat zien wat er weg zou gaan, verwijdert niks
  python3 cleanup.py           # verwijdert + schrijft redirects/opstellingen-redirects.csv

Redirects toevoegen: Webflow → Project Settings → Publishing → 301 redirects
(oude pad -> /opstellingen). Zo blijft de linkwaarde behouden en krijg je geen 404's.
"""
import os, sys, csv, argparse
from datetime import datetime, timedelta, timezone
from oa_config import RETENTION_DAYS, HUB_PATH, WEBFLOW_TOKEN, BASE, CLUBPAGINA_LEAGUES
import oa_webflow as WF
import oa_club as CLUB

REDIR = os.path.join(BASE, "redirects", "opstellingen-redirects.csv")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--days", type=int, default=RETENTION_DAYS)
    a = ap.parse_args()
    if not a.dry and not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt (of gebruik --dry)."); sys.exit(1)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=a.days)).date()
    state = WF.load_state()
    oud = []
    for fid, e in list(state.items()):
        try:
            d = datetime.fromisoformat(e.get("date")).date()
        except Exception:
            # 'date' is opgeslagen als YYYY-MM-DD
            try: d = datetime.strptime(e.get("date",""), "%Y-%m-%d").date()
            except Exception: continue
        if d <= cutoff:
            oud.append((fid, e))
    print(f"== Opschonen | ouder dan {a.days} dagen (t/m {cutoff}) | {len(oud)} artikel(en) | {'DRY' if a.dry else 'LIVE'} ==")

    # vaste clubpagina's (oa_club) blijven staan: alleen de wedstrijd uit de state halen
    for fid, e in [x for x in oud if x[1].get("evergreen")]:
        if not a.dry:
            del state[fid]; WF.save_state(state)
        print(f"  · clubpagina blijft staan, wedstrijd uit state: {e.get('match')}")
    oud = [x for x in oud if not x[1].get("evergreen")]

    def doel(e):
        """Oud Eredivisie/KKD-wedstrijdartikel -> de vaste clubpagina van de thuisploeg (als die er al is), anders de hub."""
        if e.get("league") in CLUBPAGINA_LEAGUES:
            thuis = (e.get("match") or "").split(" - ")[0]
            c = next((c for c in CLUB.load().values() if c.get("naam") == thuis and c.get("item_id")), None)
            if c:
                return f"/nieuws/{c['slug']}"
        return HUB_PATH
    tgt = HUB_PATH
    rows = [(f"www.bet-experts.nl/nieuws/{e['slug']}", f"https://www.bet-experts.nl{doel(e)}", 301) for _, e in oud]
    if a.dry:
        for fid, e in oud:
            print(f"  ○ zou verwijderen: {e.get('match')} (/nieuws/{e['slug']} -> {doel(e)})")
        print("KLAAR."); return
    if rows:
        # eerst de 301 in Cloudflare (bulk-redirectlijst 'oude_artikelen'); lukt dat niet, dan niets verwijderen
        sys.path.insert(0, os.path.join(os.path.dirname(BASE), "superodd-agent"))
        try:
            import cf_redirects
            cf_redirects.add(rows)
        except Exception as ex:
            print(f"! redirects niet gezet ({ex}) -> niets verwijderd"); sys.exit(1)
    for fid, e in oud:
        try:
            WF.delete_item(e["item_id"])
        except Exception as ex:
            print(f"  ! verwijderen mislukt: {e.get('match')} ({ex})"); continue
        del state[fid]; WF.save_state(state)
        print(f"  ✔ verwijderd: {e.get('match')}  → 301 /nieuws/{e['slug']} -> {doel(e)}")
    print("KLAAR.")

if __name__ == "__main__":
    main()
