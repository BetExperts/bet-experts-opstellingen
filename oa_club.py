# -*- coding: utf-8 -*-
"""Vaste opstellingspagina per club (Eredivisie + KKD, 24-10-2026).

Eén URL per club (/nieuws/opstelling-<club>-vandaag) die voor elke wedstrijd wordt bijgewerkt, i.p.v. een nieuw
artikel per wedstrijd: de pagina bouwt autoriteit op voor 'opstelling <club> vandaag' en gaat na de wedstrijd niet
via een 301 weg. De per-wedstrijd-state (state/opstellingen.json) blijft de motor (finalize, verversen, opruimen);
een wedstrijd met 'evergreen' schrijft naar de clubpagina's van beide ploegen, elk vanuit het eigen perspectief.

state/clubpaginas.json: team-id -> {item_id, slug, naam, fid (actuele wedstrijd), datum}."""
import json, os
from oa_config import BASE, NIEUWS_COLLECTION, WF_API
import oa_webflow as WF
import oa_match as M
import oa_build as B

STATE = os.path.join(BASE, "state", "clubpaginas.json")


def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def slug_voor(naam):
    return f"opstelling-{B.slugify(B.zoeknaam(naam))}-vandaag"


def _bestaand(slug):
    """Item-id van een bestaande clubpagina (als de state het niet weet, bv. na een git-merge)."""
    r = WF._req("GET", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items?slug={slug}")
    items = (r or {}).get("items") or []
    return items[0]["id"] if items else None


def pagina(team_id, naam):
    """(item_id of None, slug) van de clubpagina."""
    c = load().get(str(team_id))
    if c:
        return c["item_id"], c["slug"]
    slug = slug_voor(naam)
    return _bestaand(slug), slug


def schrijf(e, fid, ctx, cfg, nieuw=False, dry=False):
    """Schrijft de wedstrijd naar de clubpagina's van beide ploegen.
    nieuw=True (generate): deze wedstrijd wordt de actuele wedstrijd van beide clubs. Anders (flip/verversen) alleen
    de pagina's die nog bij deze wedstrijd horen: speelt een club inmiddels een nieuwere wedstrijd, dan blijft die staan.
    Zet e['clubs'] en retourneert [(slug, titel)]."""
    cs = load(); out = []
    for focus, tid, naam in (("home", ctx["homeId"], ctx["homeN"]), ("away", ctx["awayId"], ctx["awayN"])):
        tid = str(tid); c = cs.get(tid)
        if not nieuw and (not c or c.get("fid") != str(fid)):
            continue
        if not c:
            item_id, slug = pagina(tid, naam)
            c = {"item_id": item_id, "slug": slug, "naam": naam}
        fd, _, title = M.build_fielddata(ctx, cfg, slug=c["slug"], focus=focus)
        if dry:
            print(f"  ○ clubpagina /nieuws/{c['slug']}: {title}")
            out.append((c["slug"], title)); continue
        if c.get("item_id"):
            WF.update_live(c["item_id"], fd)
        else:
            c["item_id"] = WF.create_live(fd)
            print(f"  + nieuwe clubpagina /nieuws/{c['slug']}")
        c["fid"], c["datum"] = str(fid), e.get("date")
        cs[tid] = c
        save(cs)
        out.append((c["slug"], title))
    if not dry:
        e["clubs"] = [{"team_id": str(t), "slug": cs[str(t)]["slug"], "item_id": cs[str(t)]["item_id"]}
                      for t in (ctx["homeId"], ctx["awayId"]) if str(t) in cs and cs[str(t)].get("fid") == str(fid)]
    return out


def item_ids(e):
    """Alle CMS-items van een wedstrijd: de clubpagina's, of het losse wedstrijdartikel."""
    return [c["item_id"] for c in e.get("clubs") or []] or [e["item_id"]]
