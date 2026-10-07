# -*- coding: utf-8 -*-
"""Uitslag in de wedstrijdartikelen: zodra een wedstrijd afgelopen is, krijgen de voorbeschouwing, het
opstellingen-artikel en het live-kijken-artikel bovenaan (vóór de intro) één blok
  🏁 Uitslag: PSV – sc Heerenveen 2-1 (rust 1-0). Doelpunten: 12' G. Til (1-0), …
Wedstrijd = team-id-paar + speeldatum (zelfde sleutel als crosslink.py); de uitslag komt uit de API
(h2h van de twee teams, wedstrijd op die datum met status FT/AET/PEN). Idempotent: alleen artikelen zonder
(of met een verouderd) uitslagblok worden gepatcht. Alleen gepubliceerde, niet-draft artikelen.
  python3 uitslagen.py --dry
  python3 uitslagen.py                 # wedstrijden van de afgelopen 3 dagen (vanaf 2,5 uur na de aftrap)"""
import re, sys, html, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from oa_config import WEBFLOW_TOKEN
import oa_webflow as WF
import oa_api as api
import crosslink as CL

AMS = ZoneInfo("Europe/Amsterdam")
KLAAR = ("FT", "AET", "PEN")
BLOCK_RE = re.compile(r"<p><strong>🏁 Uitslag:.*?</p>", re.S)
esc = lambda s: html.escape(str(s or ""), quote=False)


def vind_wedstrijd(h, a, datum):
    try:
        fx = api.h2h(h, a) or []
    except Exception:
        return None
    for f in fx:
        try:
            d = datetime.fromisoformat(f["fixture"]["date"].replace("Z", "+00:00")).astimezone(AMS).date().isoformat()
        except Exception:
            continue
        if d == datum and (f["fixture"].get("status") or {}).get("short") in KLAAR:
            return f
    return None


def doelpunten(fid):
    """Doelpuntenlijst met tussenstand, gecontroleerd tegen de eindstand (eigen doelpunten: beide API-conventies)."""
    try:
        m = api.match(fid) or {}
    except Exception:
        return []
    if isinstance(m, list):
        m = m[0] if m else {}
    hid = ((m.get("teams") or {}).get("home") or {}).get("id")
    eind = ((m.get("goals") or {}).get("home"), (m.get("goals") or {}).get("away"))
    goals = [ev for ev in m.get("events") or [] if ev.get("type") == "Goal" and "Missed" not in (ev.get("detail") or "")]
    def lijst(omdraaien, met_stand):
        gh = ga = 0; out = []
        for ev in goals:
            thuis = (ev.get("team") or {}).get("id") == hid
            if omdraaien and ev.get("detail") == "Own Goal":
                thuis = not thuis
            gh, ga = (gh + 1, ga) if thuis else (gh, ga + 1)
            t = ev.get("time") or {}
            minuut = f"{t.get('elapsed')}{'+' + str(t['extra']) if t.get('extra') else ''}'"
            extra = {"Penalty": "strafschop", "Own Goal": "eigen doelpunt"}.get(ev.get("detail"))
            info = ", ".join(x for x in ([f"{gh}-{ga}"] if met_stand else []) + ([extra] if extra else []))
            out.append(f"{minuut} {((ev.get('player') or {}).get('name') or '').strip()}" + (f" ({info})" if info else ""))
        return out, (gh, ga)
    for omdraaien in (False, True):
        out, stand = lijst(omdraaien, True)
        if stand == eind:
            return out
    return lijst(False, False)[0]


def blok(f, label, home_id):
    """Uitslag in de volgorde van het artikel (thuisploeg van het artikel eerst)."""
    g, sc = f["goals"], f.get("score") or {}
    ht = sc.get("halftime") or {}
    omdraaien = str(f["teams"]["home"]["id"]) != str(home_id)
    a, b = (g["away"], g["home"]) if omdraaien else (g["home"], g["away"])
    zin = f"<p><strong>🏁 Uitslag: {esc(label)} {a}-{b}</strong>"
    if ht.get("home") is not None:
        ra, rb = (ht["away"], ht["home"]) if omdraaien else (ht["home"], ht["away"])
        zin += f" (rust {ra}-{rb})"
    st = (f["fixture"].get("status") or {}).get("short")
    if st == "AET":
        zin += ", na verlenging"
    elif st == "PEN":
        p = sc.get("penalty") or {}
        if p.get("home") is not None:
            pa, pb = (p["away"], p["home"]) if omdraaien else (p["home"], p["away"])
            zin += f", strafschoppen {pa}-{pb}"
    zin += "."
    gl = doelpunten(f["fixture"]["id"])
    if gl and not omdraaien:
        zin += " Doelpunten: " + esc(", ".join(gl)) + "."
    elif gl:
        zin += " Doelpunten: " + esc(", ".join(re.sub(r"\((\d+)-(\d+)", r"(\2-\1", x) for x in gl)) + "."
    return zin + "</p>"


def plaats(htmltxt, block):
    htmltxt = htmltxt or ""
    if BLOCK_RE.search(htmltxt):
        return BLOCK_RE.sub(lambda m: block, htmltxt, count=1)
    for m in re.finditer(r"<p>(.*?)</p>", htmltxt, re.S):
        if len(re.sub(r"<[^>]+>", "", m.group(1))) > 150:      # vóór de intro-alinea
            return htmltxt[:m.start()] + block + htmltxt[m.start():]
    return block + htmltxt


def run(dry=False, days=3, max_items=800):
    now = datetime.now(timezone.utc)
    lo, hi = now - timedelta(days=days), now - timedelta(hours=2, minutes=30)
    groepen = {}
    for it in CL.fetch_items(max_items):
        fd = it["fieldData"]; k = CL.kind(fd); ko = CL.kickoff(fd)
        if not k or not ko or not (lo <= ko <= hi) or not it.get("lastPublished") or it.get("isDraft"):
            continue
        h, a = fd.get("home-team-id"), fd.get("away-team-id")
        if not h or not a:
            continue
        key = (str(h), str(a), ko.astimezone(AMS).date().isoformat())
        groepen.setdefault(key, []).append(it)
    print(f"== Uitslagen | {len(groepen)} afgelopen wedstrijd(en) met artikelen | {'DRY' if dry else 'LIVE'} ==")
    n = 0
    for (h, a, datum), items in sorted(groepen.items(), key=lambda x: x[0][2]):
        tt = next((t for t in (CL.teams_from_title(i) for i in items) if t), None)
        label = f"{tt[0]} – {tt[1]}" if tt else None
        if not label:
            continue
        # al een uitslagblok in alle artikelen? dan geen API-call nodig
        if all(BLOCK_RE.search("".join(i["fieldData"].get(f) or "" for f in CL.FIELDS)) for i in items):
            continue
        f = vind_wedstrijd(h, a, datum)
        if not f:
            print(f"  · {label} ({datum}): nog geen eindstand"); continue
        block = blok(f, label, h)
        for it in items:
            fd = it["fieldData"]
            veld = next((x for x in CL.FIELDS if BLOCK_RE.search(fd.get(x) or "")), "content")
            new = plaats(fd.get(veld), block)
            if new == (fd.get(veld) or ""):
                continue
            n += 1
            if dry:
                print(f"  ○ {CL.kind(fd)}: {fd['slug']}\n      {block}")
            else:
                WF.update_live(it["id"], {veld: new})
                print(f"  ✔ {CL.kind(fd)}: {fd['slug']}  {re.sub(r'<[^>]+>', '', block)[:90]}")
    print(f"KLAAR — {n} artikel(en) {'zouden worden ' if dry else ''}bijgewerkt.")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--days", type=float, default=3)
    a = ap.parse_args()
    if not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt."); sys.exit(1)
    run(a.dry, a.days)


if __name__ == "__main__":
    main()
