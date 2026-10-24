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
import oa_ovandaag as OV
import oa_xi as X
from zoneinfo import ZoneInfo
NL = ZoneInfo("Europe/Amsterdam")
from datetime import datetime, timedelta, timezone
import oa_og as OG
from oa_config import LEAGUES, WEBFLOW_TOKEN, nl_name
import oa_webflow as WF
import oa_club as CLUB

LCFG = {c["worker_slug"]: c for c in LEAGUES}
EXTERN_BRON = ("footymetrics", "opstellingvandaag")   # definitief via externe bron -> later nog de API-versie
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
                or (e.get("bron") in EXTERN_BRON and e.get("date", "") >= (datetime.now() - timedelta(days=1)).date().isoformat()))
            and (not a.date or e.get("date") == a.date)}
    print(f"== Finalize | {len(todo)} kandidaat-artikel(en) | modus: {'DRY' if a.dry else 'LIVE'} ==")
    flipped = 0
    for fid, e in todo.items():
        api_ok = M.has_confirmed_lineups(fid)
        resync = e.get("definitief") and e.get("bron") in EXTERN_BRON
        if resync and not api_ok:
            continue                      # al definitief via FootyMetrics; wacht op de API-versie
        fx = api.match(fid)
        if not fx:
            print(f"  ! match niet op te halen: {fid}"); continue
        fm, fm_src = None, None
        if not api_ok:
            # API nog leeg: opstellingvandaag (meteen na de bekendmaking, ~75 min voor aftrap) of FootyMetrics
            # (vanaf ~90 min) hebben de bevestigde opstelling vaak eerder dan API-Football
            try:
                ko = datetime.fromisoformat(fx["fixture"]["date"].replace("Z", "+00:00"))
                mins = (ko - datetime.now(timezone.utc)).total_seconds() / 60
            except Exception:
                mins = 999
            if -120 < mins <= 100:
                hn, an = fx["teams"]["home"]["name"], fx["teams"]["away"]["name"]
                ymd = ko.astimezone(NL).date().isoformat()
                ov = OV.predicted([nl_name(hn), hn], [nl_name(an), an], ymd)
                if ov and ov.get("confirmed"):
                    fm, fm_src = ov, OV
                else:
                    fm, fm_src = FOOTY.confirmed(hn, an, ymd), FOOTY
            if not fm:
                print(f"  · nog geen definitieve opstelling: {e['match']} ({fid})"); continue
            print(f"     ↳ bevestigde opstelling via {'opstellingvandaag' if fm_src is OV else 'FootyMetrics'} (API nog leeg)")
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
            for k, side, tid in (("hLU", fm["home"], fx["teams"]["home"]["id"]), ("aLU", fm["away"], fx["teams"]["away"]["id"])):
                lu = M._clean_lineup(fm_src.as_lineup(side, fm["url"]))
                # namen koppelen aan de API-spelers (volledige naam, rugnummer, linie), zoals bij de vermoedelijke elf
                xi, f = X.build(side["names"], side.get("formation"), X.pool_from(M._team_lineup(tid, exclude_fixture=fid)), fm_src is OV)
                if xi:
                    lu.update({"startXI": xi, "formation": f})
                ctx[k] = lu
        # nooit 'definitief' zonder beide elftallen (cache kan net tussen twee verzoeken wisselen)
        if not ((ctx.get("hLU") or {}).get("startXI") and (ctx.get("aLU") or {}).get("startXI")):
            print(f"  · opstelling nog niet compleet binnen, volgende run opnieuw: {e['match']} ({fid})"); continue
        if e.get("stream"):
            ctx["tvgids"] = {"tv": [], "bookmakers": [e["stream"]], "gratis": False}
        fd, slug, title = M.build_fielddata(ctx, cfg, slug=e["slug"])  # slug BLIJFT gelijk
        if a.dry:
            print(f"  ○ zou flippen -> {title}")
        else:
            slugs = schrijf(e, fid, ctx, cfg, fd)
            e["definitief"] = True
            e["bron"] = ("opstellingvandaag" if fm_src is OV else "footymetrics") if fm else "api"
            og = OG.make(ctx, cfg, e.get("og_slug") or e["slug"])     # nieuwe afbeelding: 'Definitief' + echte formaties
            if og: e["og"] = og
            WF.save_state(state)
            print(f"  ✔ definitief: {title}")
            PING.extend(f"https://www.bet-experts.nl/nieuws/{s_}" for s_ in slugs)
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

def schrijf(e, fid, ctx, cfg, fd):
    """Wedstrijdartikel bijwerken, of bij een vaste clubpagina (oa_club) de pagina's van beide clubs. -> slugs"""
    if e.get("evergreen"):
        return [s_ for s_, _ in CLUB.schrijf(e, fid, ctx, cfg)]
    WF.update_live(e["item_id"], fd)
    return [e["slug"]]

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
        vandaag = ko.astimezone().date() == datetime.now().date() and not e.get("titel_vandaag")
        if sig == e.get("xi_sig") and not vandaag:
            continue
        first = "xi_sig" not in e
        e["xi_sig"], e["xi_extern"] = sig, extern
        if first and not vandaag:
            continue                               # eerste meting: alleen vastleggen, artikel is net gemaakt
        if vandaag:
            e["titel_vandaag"] = True              # wedstrijddag: titel/meta eenmalig naar 'Opstelling X vandaag tegen Y' 
        if e.get("stream"):
            ctx["tvgids"] = {"tv": [], "bookmakers": [e["stream"]], "gratis": False}
        fd, slug, title = M.build_fielddata(ctx, cfg, slug=e["slug"])
        if dry:
            print(f"  ○ zou verversen (vermoedelijke elf gewijzigd): {title}")
        else:
            slugs = schrijf(e, fid, ctx, cfg, fd)
            og = OG.make(ctx, cfg, e.get("og_slug") or e["slug"])
            if og: e["og"] = og
            print(f"  ↻ vermoedelijke opstelling bijgewerkt: {title}")
            PING.extend(f"https://www.bet-experts.nl/nieuws/{s_}" for s_ in slugs)
        n += 1
    if not dry:
        WF.save_state(state)
    print(f"Verversen: {n} artikel(en) met gewijzigde vermoedelijke opstelling.")
    return n

if __name__ == "__main__":
    main()
