# -*- coding: utf-8 -*-
"""Verzamelt alle data voor één wedstrijd en bouwt de Webflow-velddata."""
import re
from datetime import datetime, timezone
import oa_api as api
from oa_config import club_slug, RUBRIEK_ID
import oa_build as B

def _pct(s):
    try: return int(str(s).replace("%","").strip())
    except: return 0

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
                out.append(lu); break
        if len(out) >= want: break
    return out

def gather(fx, definitief=False):
    """fx = een fixture-object uit /api/fixtures (of /api/match)."""
    fixture = fx.get("fixture", {}); teams = fx.get("teams", {}); league = fx.get("league", {})
    fid = fixture.get("id")
    home = teams.get("home", {}); away = teams.get("away", {})
    homeId, awayId = home.get("id"), away.get("id")
    homeN, awayN = home.get("name"), away.get("name")
    dt = B._local(fixture.get("date"))
    ven = fixture.get("venue", {}) or {}
    venue = ven.get("name"); city = ven.get("city") or ""
    m = re.search(r"(\d+)", league.get("round", "") or "")
    ronde = m.group(1) if m else "?"

    pred = api.predictions(fid) or {}
    pr = pred.get("predictions", {}) or {}
    pct = pr.get("percent", {}) or {}
    pH, pD, pA = _pct(pct.get("home")), _pct(pct.get("draw")), _pct(pct.get("away"))
    tt = pred.get("teams", {}) or {}
    hForm = ((tt.get("home", {}) or {}).get("league", {}) or {}).get("form", "") or ""
    aForm = ((tt.get("away", {}) or {}).get("league", {}) or {}).get("form", "") or ""
    hForm, aForm = hForm[-5:], aForm[-5:]
    h2h = pred.get("h2h") or api.h2h(homeId, awayId)

    if definitief:
        lus = api.lineups(fid)
        def pick(tid):
            for lu in lus:
                if str((lu.get("team") or {}).get("id")) == str(tid) and lu.get("startXI"):
                    return lu
            return None
        hLU, aLU = pick(homeId), pick(awayId)
        hPrev = aPrev = None
    else:
        hl = _team_lineup(homeId, exclude_fixture=fid); al = _team_lineup(awayId, exclude_fixture=fid)
        hLU = hl[0] if hl else None; hPrev = hl[1] if len(hl) > 1 else None
        aLU = al[0] if al else None; aPrev = al[1] if len(al) > 1 else None

    return {
        "fid": fid, "homeId": homeId, "awayId": awayId, "homeN": homeN, "awayN": awayN,
        "hSlug": club_slug(homeId, homeN), "aSlug": club_slug(awayId, awayN),
        "compSlug": None, "compN": None,  # ingevuld door caller (league config)
        "dt": dt, "venue": venue, "city": city, "ronde": ronde, "definitief": definitief,
        "pH": pH, "pD": pD, "pA": pA, "hForm": hForm, "aForm": aForm,
        "hLU": hLU, "aLU": aLU, "hPrev": hPrev, "aPrev": aPrev,
        "hInj": api.injuries_team(homeId), "aInj": api.injuries_team(awayId),
        "h2h": h2h,
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
    dt = ctx["dt"]; definitief = ctx["definitief"]
    content, content2, content3 = B.build_content(ctx)
    title = B.build_title(definitief, ctx["homeN"], ctx["awayN"], ctx["city"] or ctx["venue"] or "", ctx["pH"], ctx["pA"])
    samenvatting = B.build_samenvatting(definitief, ctx["homeN"], ctx["awayN"], league_cfg["naam"], dt)
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
