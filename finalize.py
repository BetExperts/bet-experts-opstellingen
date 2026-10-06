# -*- coding: utf-8 -*-
"""Flipt bestaande artikelen naar de DEFINITIEVE opstelling zodra die binnen is.
Draai dit op wedstrijddag, bijv. elk half uur vanaf ~2u voor de vroegste aftrap.
  python3 finalize.py --dry
  python3 finalize.py            # live updaten + herpubliceren
Verwerkt standaard alle nog-niet-definitieve items uit state (van vandaag)."""
import sys, argparse
import oa_api as api
import oa_match as M
import oa_footy as FOOTY
from datetime import datetime, timedelta, timezone
import oa_og as OG
from oa_config import LEAGUES, WEBFLOW_TOKEN
import oa_webflow as WF

LCFG = {c["worker_slug"]: c for c in LEAGUES}
PING = []   # bijgewerkte URL's -> IndexNow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if not a.dry and not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt (of gebruik --dry)."); sys.exit(1)

    state = WF.load_state()
    # nog niet definitief, of definitief via FootyMetrics en nog niet bijgewerkt met de API-opstelling
    todo = {fid: e for fid, e in state.items()
            if (not e.get("definitief")
                or (e.get("bron") == "footymetrics" and e.get("date", "") >= (datetime.now() - timedelta(days=1)).date().isoformat()))
            and (not a.date or e.get("date") == a.date)}
    print(f"== Finalize | {len(todo)} kandidaat-artikel(en) | modus: {'DRY' if a.dry else 'LIVE'} ==")
    flipped = 0
    for fid, e in todo.items():
        api_ok = M.has_confirmed_lineups(fid)
        resync = e.get("definitief") and e.get("bron") == "footymetrics"
        if resync and not api_ok:
            continue                      # al definitief via FootyMetrics; wacht op de API-versie
        fx = api.match(fid)
        if not fx:
            print(f"  ! match niet op te halen: {fid}"); continue
        fm = None
        if not api_ok:
            # API nog leeg: FootyMetrics heeft de bevestigde opstelling vaak eerder (vanaf ~90 min voor aftrap)
            try:
                ko = datetime.fromisoformat(fx["fixture"]["date"].replace("Z", "+00:00"))
                mins = (ko - datetime.now(timezone.utc)).total_seconds() / 60
            except Exception:
                mins = 999
            if -120 < mins <= 90:
                fm = FOOTY.confirmed(fx["teams"]["home"]["name"], fx["teams"]["away"]["name"], ko.date().isoformat())
            if not fm:
                print(f"  · nog geen definitieve opstelling: {e['match']} ({fid})"); continue
            print(f"     ↳ bevestigde opstelling via FootyMetrics (API nog leeg)")
        # competitie-info: eerst uit de state (werkt ook voor losse test-wedstrijden),
        # anders uit de LEAGUES-config
        cfg = LCFG.get(e.get("league"))
        if not cfg:
            cfg = {"worker_slug": e.get("league", ""),
                   "comp_slug": e.get("comp_slug", "eredivisie"),
                   "naam": e.get("naam", "Eredivisie"),
                   "comp_id": e.get("comp_id"), "vriendschappelijk": e.get("vriendschappelijk", False)}
        ctx = M.gather(fx, definitief=True)
        if fm:
            ctx["hLU"] = M._clean_lineup(FOOTY.as_lineup(fm["home"], fm["url"]))
            ctx["aLU"] = M._clean_lineup(FOOTY.as_lineup(fm["away"], fm["url"]))
        # nooit 'definitief' zonder beide elftallen (cache kan net tussen twee verzoeken wisselen)
        if not ((ctx.get("hLU") or {}).get("startXI") and (ctx.get("aLU") or {}).get("startXI")):
            print(f"  · opstelling nog niet compleet binnen, volgende run opnieuw: {e['match']} ({fid})"); continue
        if e.get("stream"):
            ctx["tvgids"] = {"tv": [], "bookmakers": [e["stream"]], "gratis": False}
        fd, slug, title = M.build_fielddata(ctx, cfg, slug=e["slug"])  # slug BLIJFT gelijk
        if a.dry:
            print(f"  ○ zou flippen -> {title}")
        else:
            WF.update_live(e["item_id"], fd)
            e["definitief"] = True
            e["bron"] = "footymetrics" if fm else "api"
            og = OG.make(ctx, cfg, e["slug"])     # nieuwe afbeelding: 'Definitief' + echte formaties
            if og: e["og"] = og
            WF.save_state(state)
            print(f"  ✔ definitief: {title}")
            PING.append(f"https://www.bet-experts.nl/nieuws/{e['slug']}")
        flipped += 1
    print(f"\nKLAAR — {flipped} artikel(en) geflipt naar definitief.")
    ververst = 0 if a.date else refresh_predicted(state, a.dry)
    if PING and not a.dry:
        import indexnow
        indexnow.ping(PING)
    if (flipped or ververst) and not a.dry:
        # de flip herschrijft de content -> wedstrijd-links (voorbeschouwing/live) opnieuw plaatsen
        import crosslink
        print("\n-- wedstrijd-links opnieuw plaatsen --")
        crosslink.run(days=1, back=6, max_items=400)

REFRESH_MIN = 55     # vermoedelijke opstellingen op de wedstrijddag elk uur verversen

def _xi_sig(ctx):
    sig = []
    for k in ("hLU", "aLU"):
        lu = ctx.get(k) or {}
        sig.append((lu.get("formation") or "") + ":" + ",".join((p.get("player") or {}).get("name", "") for p in lu.get("startXI") or []))
    return "|".join(sig)

def refresh_predicted(state, dry=False):
    """Nog niet definitieve artikelen met aftrap in de komende 24 uur: elk uur de vermoedelijke elf opnieuw
    ophalen (de externe bron werkt die bij na persconferenties) en het artikel alleen bijwerken als er iets
    veranderd is. Nooit terugvallen van een externe voorspelling naar 'laatst gespeelde elf'."""
    now = datetime.now(timezone.utc); n = 0
    for fid, e in state.items():
        if e.get("definitief"):
            continue
        last = e.get("ververst")
        if last and (now - datetime.fromisoformat(last)).total_seconds() < REFRESH_MIN * 60:
            continue
        fx = api.match(fid)
        if not fx:
            continue
        try:
            ko = datetime.fromisoformat(fx["fixture"]["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if not (now < ko < now + timedelta(hours=24)):
            continue
        cfg = LCFG.get(e.get("league")) or {"worker_slug": e.get("league", ""), "comp_slug": e.get("comp_slug", "eredivisie"),
                                            "naam": e.get("naam", "Eredivisie"), "comp_id": e.get("comp_id"),
                                            "vriendschappelijk": e.get("vriendschappelijk", False)}
        ctx = M.gather(fx, definitief=False)
        e["ververst"] = now.isoformat(timespec="seconds")
        extern = (ctx.get("hLU") or {}).get("source") in ("footymetrics", "extern")
        if e.get("xi_extern") and not extern:
            continue                               # bron (even) leeg: oude voorspelling laten staan
        sig = _xi_sig(ctx)
        if sig == e.get("xi_sig"):
            continue
        first = "xi_sig" not in e
        e["xi_sig"], e["xi_extern"] = sig, extern
        if first:
            continue                               # eerste meting: alleen vastleggen, artikel is net gemaakt
        if e.get("stream"):
            ctx["tvgids"] = {"tv": [], "bookmakers": [e["stream"]], "gratis": False}
        fd, slug, title = M.build_fielddata(ctx, cfg, slug=e["slug"])
        if dry:
            print(f"  ○ zou verversen (vermoedelijke elf gewijzigd): {title}")
        else:
            WF.update_live(e["item_id"], fd)
            og = OG.make(ctx, cfg, e["slug"])
            if og: e["og"] = og
            print(f"  ↻ vermoedelijke opstelling bijgewerkt: {title}")
            PING.append(f"https://www.bet-experts.nl/nieuws/{e['slug']}")
        n += 1
    if not dry:
        WF.save_state(state)
    print(f"Verversen: {n} artikel(en) met gewijzigde vermoedelijke opstelling.")
    return n

if __name__ == "__main__":
    main()
