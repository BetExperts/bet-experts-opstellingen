# -*- coding: utf-8 -*-
"""Handmatig: deelafbeeldingen maken voor bestaande (aankomende) opstellingen-artikelen,
ZONDER de artikeltekst te herschrijven. Daarna committen + pushen en attach_og.py draaien.

  python3 backfill_og.py                  # alle artikelen vanaf vandaag
  python3 backfill_og.py --vanaf 2026-10-01
"""
import sys
from datetime import date
import oa_api as api
import oa_match as M
import oa_og as OG
import oa_webflow as WF
from oa_config import LEAGUES

def main():
    vanaf = sys.argv[sys.argv.index("--vanaf") + 1] if "--vanaf" in sys.argv else date.today().isoformat()
    lcfg = {c["worker_slug"]: c for c in LEAGUES}
    state = WF.load_state()
    for fid, e in sorted(state.items(), key=lambda x: x[1].get("date", "")):
        if e.get("date", "") < vanaf or e.get("og"):
            continue
        cfg = lcfg.get(e.get("league")) or {"naam": e.get("naam", ""), "vriendschappelijk": e.get("vriendschappelijk")}
        fx = api.match(fid)
        if not fx:
            print(f"  · overgeslagen: {e['slug']}"); continue
        ctx = M.gather(fx, definitief=bool(e.get("definitief")))
        og = OG.make(ctx, cfg, e["slug"])
        if og:
            e["og"] = og; WF.save_state(state)
            print(f"  ✔ {og}")

if __name__ == "__main__":
    main()
