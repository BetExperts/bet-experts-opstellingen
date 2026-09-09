# -*- coding: utf-8 -*-
"""Flipt bestaande artikelen naar de DEFINITIEVE opstelling zodra die binnen is.
Draai dit op wedstrijddag, bijv. elk half uur vanaf ~2u voor de vroegste aftrap.
  python3 finalize.py --dry
  python3 finalize.py            # live updaten + herpubliceren
Verwerkt standaard alle nog-niet-definitieve items uit state (van vandaag)."""
import sys, argparse
import oa_api as api
import oa_match as M
from oa_config import LEAGUES, WEBFLOW_TOKEN
import oa_webflow as WF

LCFG = {c["worker_slug"]: c for c in LEAGUES}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if not a.dry and not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt (of gebruik --dry)."); sys.exit(1)

    state = WF.load_state()
    todo = {fid: e for fid, e in state.items()
            if not e.get("definitief") and (not a.date or e.get("date") == a.date)}
    print(f"== Finalize | {len(todo)} kandidaat-artikel(en) | modus: {'DRY' if a.dry else 'LIVE'} ==")
    flipped = 0
    for fid, e in todo.items():
        if not M.has_confirmed_lineups(fid):
            print(f"  · nog geen definitieve opstelling: {e['match']} ({fid})"); continue
        # data verzamelen mét bevestigde opstellingen
        fx = api.match(fid)
        if not fx:
            print(f"  ! match niet op te halen: {fid}"); continue
        # competitie-info: eerst uit de state (werkt ook voor losse test-wedstrijden),
        # anders uit de LEAGUES-config
        cfg = LCFG.get(e.get("league"))
        if not cfg:
            cfg = {"worker_slug": e.get("league", ""),
                   "comp_slug": e.get("comp_slug", "eredivisie"),
                   "naam": e.get("naam", "Eredivisie")}
        ctx = M.gather(fx, definitief=True)
        fd, slug, title = M.build_fielddata(ctx, cfg, slug=e["slug"])  # slug BLIJFT gelijk
        if a.dry:
            print(f"  ○ zou flippen -> {title}")
        else:
            WF.update_live(e["item_id"], fd)
            e["definitief"] = True; WF.save_state(state)
            print(f"  ✔ definitief: {title}")
        flipped += 1
    print(f"\nKLAAR — {flipped} artikel(en) geflipt naar definitief.")

if __name__ == "__main__":
    main()
