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
from oa_config import RETENTION_DAYS, HUB_PATH, WEBFLOW_TOKEN, BASE
import oa_webflow as WF

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

    rows = []
    for fid, e in oud:
        oldpath = f"/nieuws/{e['slug']}"
        if a.dry:
            print(f"  ○ zou verwijderen: {e.get('match')} ({oldpath})")
        else:
            WF.delete_item(e["item_id"])
            rows.append([oldpath, HUB_PATH])
            del state[fid]; WF.save_state(state)
            print(f"  ✔ verwijderd: {e.get('match')}  → redirect {oldpath} -> {HUB_PATH}")

    if rows:
        os.makedirs(os.path.dirname(REDIR), exist_ok=True)
        new = not os.path.exists(REDIR)
        with open(REDIR, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new: w.writerow(["old_path", "redirect_to"])
            w.writerows(rows)
        print(f"\n{len(rows)} redirect(s) toegevoegd aan {REDIR} — voeg deze toe in Webflow → Publishing → 301 redirects.")
    print("KLAAR.")

if __name__ == "__main__":
    main()
