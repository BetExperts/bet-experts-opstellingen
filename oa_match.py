# -*- coding: utf-8 -*-
"""Verzamelt alle data voor één wedstrijd en bouwt de Webflow-velddata."""
import re
from datetime import datetime, timezone, timedelta
import oa_api as api
import oa_footy as FOOTY
from oa_config import club_slug, RUBRIEK_ID, nl_name, fix_mojibake, stadion_nl, stad_nl
import oa_build as B
from tvgids import TvGids

_GIDS = TvGids()   # waaroptv.nl — één keer laden per run (generate én finalize)

def _pct(s):
    try: return int(str(s).replace("%","").strip())
    except: return 0

_ROUND_NL = {
    "round of 64": "1/32 finale", "round of 32": "1/16 finale", "round of 16": "achtste finale",
    "quarter-finals": "kwartfinale", "quarter finals": "kwartfinale",
    "semi-finals": "halve finale", "semi finals": "halve finale",
    "final": "finale", "3rd round": "3e ronde", "4th round": "4e ronde", "5th round": "5e ronde",
}
def _ronde_labels(round_raw, ronde_num):
    """Retourneert (label, introzin) — league: 'Speelronde 6' / 'speelronde 6';
    beker: '1/16 finale' / 'de 1/16 finale'."""
    low = (round_raw or "").strip().lower()
    if "regular season" in low or "matchday" in low or not low:
        n = ronde_num if ronde_num != "?" else ""
        return (f"Speelronde {n}".strip(), f"speelronde {n}".strip())
    lg = re.match(r"league\s+([a-d])\s*-\s*(\d+)", low)          # Nations League: 'League A - 1'
    if lg:
        L, n = lg.group(1).upper(), lg.group(2)
        return (f"League {L}, speelronde {n}", f"speelronde {n} van League {L}")
    gs = re.match(r"group stage\s*-\s*(\d+)", low)               # kwalificatie: 'Group Stage - 1'
    if gs:
        return (f"Groepsfase, speelronde {gs.group(1)}", f"speelronde {gs.group(1)} van de groepsfase")
    for k, v in _ROUND_NL.items():
        if k in low:
            return (v[0].upper() + v[1:], f"de {v}")
    return (round_raw, f"de {round_raw}")

def _clean_lineup(lu):
    """Kopie van een opstelling met gerepareerde spelersnamen (mojibake)."""
    if not lu:
        return lu
    lu = dict(lu)
    xi = []
    for pp in lu.get("startXI") or []:
        pp = dict(pp); pl = dict(pp.get("player") or {})
        pl["name"] = fix_mojibake(pl.get("name"))
        pp["player"] = pl; xi.append(pp)
    lu["startXI"] = xi
    return lu

INJ_WINDOW_DAYS = 14   # alleen afwezigen uit de laatste twee weken vóór de aftrap

def _injuries(fid, team_id, kickoff, fx_inj):
    """Afwezigen van één ploeg voor deze wedstrijd.
    1) wedstrijd-specifieke lijst (/injuries/{fixture}) als die voor deze ploeg gevuld is;
    2) anders de teamlijst, maar alleen meldingen met een fixture-datum binnen
       INJ_WINDOW_DAYS dagen vóór de aftrap (oude, allang herstelde blessures vallen weg),
       en daarvan alleen die van de recentste wedstrijd.
    Per speler telt de recentste melding."""
    own = [i for i in fx_inj if str((i.get("team") or {}).get("id")) == str(team_id)]
    if not own:
        lo = kickoff - timedelta(days=INJ_WINDOW_DAYS)
        for i in api.injuries_team(team_id):
            try:
                d = datetime.fromisoformat(((i.get("fixture") or {}).get("date") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if lo <= d <= kickoff + timedelta(hours=3):
                own.append(i)
        # alleen de meldingen van de recentste wedstrijd in dat venster: wie daar niet meer
        # op de lijst staat, is kennelijk hersteld (langdurig geblesseerden staan er elke keer op)
        if own:
            last = max((i.get("fixture") or {}).get("date") or "" for i in own)
            own = [i for i in own if ((i.get("fixture") or {}).get("date") or "") == last]
    own.sort(key=lambda i: (i.get("fixture") or {}).get("date") or "")
    latest = {}
    for i in own:                          # recentste melding per speler wint
        pl = dict(i.get("player") or {})
        pl["name"] = fix_mojibake(pl.get("name"))
        key = pl.get("id") or pl.get("name")
        if key:
            latest[key] = dict(i, player=pl)
    return list(latest.values())

def _team_lineup(team_id, exclude_fixture=None, want=2):
    """Haal de laatste 'want' opstellingen van een team op (recentste eerst)."""
    fixtures = api.team_form(team_id)
    fixtures = [f for f in fixtures if f.get("fixture", {}).get("id") != exclude_fixture]
    fixtures.sort(key=lambda f: f.get("fixture", {}).get("date", ""), reverse=True)
    out = []
    for f in fixtures[:5]:
        fid = f.get("fixture", {}).get("id")
        for lu in api.lineups(fid):
            if str((lu.get("team") or {}).get("id")) == str(team_id) and (lu.get("startXI")):
                out.append(_clean_lineup(lu)); break
        if len(out) >= want: break
    return out

def _form_string(team_id, before=None):
    """Leidt W/D/L-vorm (laatste 5, chronologisch, alle competities) af uit /api/team-form.
    before = ISO-aftrap: alleen wedstrijden die vóór deze wedstrijd gespeeld zijn."""
    fixtures = api.team_form(team_id)
    done = [f for f in fixtures
            if ((f.get("fixture", {}).get("status", {}) or {}).get("short") in ("FT", "AET", "PEN"))
            and (not before or (f.get("fixture", {}).get("date") or "") < before)]
    done.sort(key=lambda f: f.get("fixture", {}).get("date", ""))
    out = ""
    for f in done[-5:]:
        t = f.get("teams", {}); g = f.get("goals", {})
        gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            continue
        home = str((t.get("home") or {}).get("id")) == str(team_id)
        my, opp = (gh, ga) if home else (ga, gh)
        out += "W" if my > opp else ("L" if my < opp else "D")
    return out

def gather(fx, definitief=False):
    """fx = een fixture-object uit /api/fixtures (of /api/match)."""
    fixture = fx.get("fixture", {}); teams = fx.get("teams", {}); league = fx.get("league", {})
    fid = fixture.get("id")
    home = teams.get("home", {}); away = teams.get("away", {})
    homeId, awayId = home.get("id"), away.get("id")
    homeN, awayN = nl_name(home.get("name")), nl_name(away.get("name"))   # landen -> Nederlands
    dt = B._local(fixture.get("date"))
    ven = fixture.get("venue", {}) or {}
    venue = stadion_nl(ven.get("name")); city = stad_nl(ven.get("city")) or ""
    round_raw = league.get("round", "") or ""
    m = re.search(r"(\d+)\s*$", round_raw) or re.search(r"(\d+)", round_raw)
    ronde = m.group(1) if m else "?"
    ronde_txt, ronde_intro = _ronde_labels(round_raw, ronde)

    pred = api.predictions(fid) or {}
    pr = pred.get("predictions", {}) or {}
    pct = pr.get("percent", {}) or {}
    pH, pD, pA = _pct(pct.get("home")), _pct(pct.get("draw")), _pct(pct.get("away"))
    # vorm: altijd de laatste 5 gespeelde wedstrijden over álle competities (chronologisch,
    # recentste rechts) — league.form uit predictions telt alleen de eigen competitie mee
    hForm, aForm = _form_string(homeId, fixture.get("date")), _form_string(awayId, fixture.get("date"))
    h2h = pred.get("h2h") or api.h2h(homeId, awayId)
    # betrouwbare voorspelling? (API geeft soms "No predictions available" + 33/33/33)
    adv = (pr.get("advice") or "").strip().lower()
    # geen echte voorspelling: 0% voor een uitkomst (bv. 50/50/0), 33/33/33, het standaardpatroon
    # 10/45/45 of een 'double chance'-advies (de API weet het dan eigenlijk niet)
    has_pred = bool((pH or pD or pA) and not adv.startswith("no prediction") and not (pH == pD == pA)
                    and 0 not in (pH, pD, pA)
                    and sorted((pH, pD, pA)) != [10, 45, 45]
                    and "double chance" not in adv)

    if definitief:
        lus = api.lineups(fid)
        def pick(tid):
            for lu in lus:
                if str((lu.get("team") or {}).get("id")) == str(tid) and lu.get("startXI"):
                    return lu
            return None
        hLU, aLU = _clean_lineup(pick(homeId)), _clean_lineup(pick(awayId))
        hPrev = aPrev = None
    else:
        hl = _team_lineup(homeId, exclude_fixture=fid); al = _team_lineup(awayId, exclude_fixture=fid)
        hLU = hl[0] if hl else None; hPrev = hl[1] if len(hl) > 1 else None
        aLU = al[0] if al else None; aPrev = al[1] if len(al) > 1 else None
        # Betere voorspelling van FootyMetrics (met toestemming)? Dan die elf + formatie gebruiken;
        # de laatst gespeelde opstelling dient dan als vergelijking ('wijzigingen t.o.v. vorige duel').
        fm = FOOTY.predicted(home.get("name"), away.get("name"), dt.date().isoformat())
        if fm:
            # vergelijkingsmateriaal: de laatste twee gespeelde basiselftallen (footy_note kiest de best passende)
            hPrev, aPrev = hl, al
            hLU = _clean_lineup(FOOTY.as_lineup(fm["home"], fm["url"]))
            aLU = _clean_lineup(FOOTY.as_lineup(fm["away"], fm["url"]))
            print(f"     ↳ vermoedelijke opstellingen via FootyMetrics ({hLU['formation']} / {aLU['formation']})")

    fx_inj = api.injuries_fixture(fid) if fid else []
    ko = datetime.fromisoformat((fixture.get("date") or "").replace("Z", "+00:00"))
    return {
        "fid": fid, "homeId": homeId, "awayId": awayId, "homeN": homeN, "awayN": awayN,
        "homeApi": home.get("name"), "awayApi": away.get("name"),   # Engelse API-naam (voor de vlag)
        "hSlug": club_slug(homeId, homeN), "aSlug": club_slug(awayId, awayN),
        "compSlug": None, "compN": None,  # ingevuld door caller (league config)
        "dt": dt, "venue": venue, "city": city, "ronde": ronde,
        "ronde_txt": ronde_txt, "ronde_intro": ronde_intro, "definitief": definitief,
        "pH": pH, "pD": pD, "pA": pA, "has_pred": has_pred, "hForm": hForm, "aForm": aForm,
        "hLU": hLU, "aLU": aLU, "hPrev": hPrev, "aPrev": aPrev,
        "hInj": _injuries(fid, homeId, ko, fx_inj), "aInj": _injuries(fid, awayId, ko, fx_inj),
        "h2h": h2h,
        "tvgids": _GIDS.lookup(homeN, awayN, dt),   # exacte zender (of None -> geen tv-regel)
    }

def has_confirmed_lineups(fid):
    """True als de definitieve opstellingen (beide ploegen) binnen zijn."""
    lus = api.lineups(fid)
    return len([lu for lu in lus if lu.get("startXI")]) >= 2

def build_fielddata(ctx, league_cfg, slug=None):
    """Bouw de Webflow fieldData voor create/update."""
    import random
    random.seed(str(ctx["fid"]))   # deterministische titel-hook per wedstrijd
    ctx = dict(ctx)
    ctx["compSlug"] = league_cfg["comp_slug"]; ctx["compN"] = league_cfg["naam"]
    ctx["vriendschappelijk"] = league_cfg.get("vriendschappelijk", False)
    ctx["geen_ronde"] = league_cfg.get("geen_ronde", False)   # API-ronde onbruikbaar (bv. EK onder 21)
    dt = ctx["dt"]; definitief = ctx["definitief"]
    content, content2, content3 = B.build_content(ctx)
    title = B.build_title(definitief, ctx["homeN"], ctx["awayN"], ctx["city"] or ctx["venue"] or "", ctx["pH"], ctx["pA"], ctx.get("has_pred", True))
    samenvatting = B.build_samenvatting(definitief, ctx["homeN"], ctx["awayN"], league_cfg["naam"], dt,
                                        ctx.get("has_pred", True))
    if not slug:
        hs = ctx["hSlug"] or B.slugify(ctx["homeN"]); as_ = ctx["aSlug"] or B.slugify(ctx["awayN"])
        slug = B.build_slug(hs, as_, dt)
    fd = {
        "name": title, "slug": slug,
        "content": content, "content-2": content2, "content-3": content3,
        "samenvatting": samenvatting,
        "fixture-id": str(ctx["fid"]),
        "home-team-id": str(ctx["homeId"]), "away-team-id": str(ctx["awayId"]),
        "league-slug": league_cfg["comp_slug"],
        "publicatiedatum": datetime.now(timezone.utc).isoformat(),
        "datum-tijd-van-wedstrijd": ctx["dt"].isoformat(),
        "tijd-wedstrijd": B.nl_tijd(ctx["dt"]),
    }
    if RUBRIEK_ID:
        fd["rubriek"] = RUBRIEK_ID
    if league_cfg.get("comp_id"):
        fd["competitie"] = league_cfg["comp_id"]   # referentieveld voor hub-filter/sortering
    return fd, slug, title
