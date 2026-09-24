# -*- coding: utf-8 -*-
"""Wedstrijd-links: koppelt per wedstrijd de voorbeschouwing, het opstelling-artikel
en het live-kijken-artikel aan elkaar. Elk artikel krijgt één blok
  🔗 Meer over X – Y: <voorspelling> · <opstellingen> · <live kijken>
met links naar de ándere artikelen van dezelfde wedstrijd.
Wedstrijd = team-id-paar + speeldatum (Amsterdam). Idempotent: een bestaand blok wordt
vervangen, niet gedupliceerd; alleen gewijzigde artikelen worden gepatcht.
Veilig: artikelen die (nog) niet live zijn (gepland/draft) worden niet aangeraakt en
er wordt ook niet naar gelinkt.
  python3 crosslink.py --dry
  python3 crosslink.py                  # wedstrijden van nu-6u t/m +3 dagen
  python3 crosslink.py --days 7 --back 48"""
import re, sys, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from oa_config import WEBFLOW_TOKEN, NIEUWS_COLLECTION, WF_API
import oa_webflow as WF

AMS = ZoneInfo("Europe/Amsterdam")
SPACER = "<p>‍</p>"
BLOCK_RE = re.compile(r"(?:<p>‍</p>)?<p>🔗 <strong>Meer over .*?</p>", re.S)
LEES_OOK_RE = re.compile(r"<p>📋 <strong>Lees ook:</strong>.*?</p>", re.S)   # oud blok live-kijken
LIVE_RE = re.compile(r"-live(-gratis)?-kijken-\d{2}-\d{2}-\d{4}$")
FIELDS = ("content", "content-2", "content-3")

def kind(fd):
    slug = fd.get("slug") or ""
    if fd.get("voorbeschouwing-2"): return "voorb"
    if slug.startswith("opstelling-"): return "opst"
    if LIVE_RE.search(slug): return "live"
    return None

def kickoff(fd):
    s = fd.get("datum-tijd-van-wedstrijd")
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None

def fetch_items(max_items):
    out, offset = [], 0
    while offset < max_items:
        page = WF._req("GET", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items"
                              f"?limit=100&offset={offset}&sortBy=lastPublished&sortOrder=desc")
        items = (page or {}).get("items") or []
        if not items: break
        out += items; offset += len(items)
        if offset >= ((page.get("pagination") or {}).get("total") or 0): break
    return out

PREFIX_RE = re.compile(r"^(?:(?:vermoedelijke|definitieve|officiële)\s+)?opstelling(?:en)?\s+|^wedtips\s+"
                       r"|^(?:waar kijk je|kun je|is|hoe kijk je)\s+", re.I)
TEAMS_RE = re.compile(r"^(.+?) [–-] (.+?)(?=\s+(?:gratis|live|kijken|voorspelling)\b|\s*[:|(,?]|$)", re.I)

def teams_from_title(it):
    """'X – Y' uit de artikelnaam (zonder 'Vermoedelijke opstelling'/'Wedtips'), voor de ankertekst."""
    name = PREFIX_RE.sub("", (it["fieldData"].get("name") or "").strip())
    m = TEAMS_RE.search(name)
    return (m.group(1).strip(), m.group(2).strip()) if m else None

def build_block(group, self_kind, label):
    parts = []
    if "voorb" in group and self_kind != "voorb":
        parts.append(f'<a href="/nieuws/{group["voorb"]["fieldData"]["slug"]}">Voorspelling en odds {label}</a>')
    if "opst" in group and self_kind != "opst":
        parts.append(f'<a href="/nieuws/{group["opst"]["fieldData"]["slug"]}">Opstellingen {label}</a>')
    if "live" in group and self_kind != "live":
        parts.append(f'<a href="/nieuws/{group["live"]["fieldData"]["slug"]}">{label} gratis live kijken</a>')
    if not parts: return None
    return f"<p>🔗 <strong>Meer over {label}:</strong> " + " · ".join(parts) + "</p>"

def place(html, block):
    """Vervang een bestaand blok, of zet het na de intro-alinea."""
    html = html or ""
    if BLOCK_RE.search(html):
        spacer = SPACER if BLOCK_RE.search(html).group(0).startswith(SPACER) else ""
        return BLOCK_RE.sub(lambda m: spacer + block, html, count=1)
    if LEES_OOK_RE.search(html):
        return LEES_OOK_RE.sub(lambda m: block, html, count=1)
    spacer = SPACER if SPACER in html else ""
    for m in re.finditer(r"<p>(.*?)</p>", html, re.S):
        if len(re.sub(r"<[^>]+>", "", m.group(1))) > 150:   # intro-alinea
            return html[:m.end()] + spacer + block + html[m.end():]
    return None

def run(dry=False, days=3, back=6, max_items=800):
    """Legt de wedstrijd-links aan/bij. Retourneert het aantal bijgewerkte artikelen."""
    now = datetime.now(timezone.utc)
    lo, hi = now - timedelta(hours=back), now + timedelta(days=days)

    groups = {}
    for it in fetch_items(max_items):
        fd = it["fieldData"]; k = kind(fd); ko = kickoff(fd)
        if not k or not ko or not (lo <= ko <= hi): continue
        if not it.get("lastPublished"): continue            # gepland / nooit live: niet linken
        h, w = fd.get("home-team-id"), fd.get("away-team-id")
        if not h or not w: continue
        key = (tuple(sorted([str(h), str(w)])), ko.astimezone(AMS).date().isoformat())
        groups.setdefault(key, {}).setdefault(k, it)         # nieuwste per soort wint

    print(f"== Wedstrijd-links | {len(groups)} wedstrijd(en) in venster | modus: {'DRY' if dry else 'LIVE'} ==")
    changed = 0
    for key, g in sorted(groups.items(), key=lambda x: x[0][1]):
        if len(g) < 2: continue
        tt = next((t for t in (teams_from_title(g[k]) for k in ("opst", "live", "voorb") if k in g) if t), None)
        label = f"{tt[0]} – {tt[1]}" if tt else "deze wedstrijd"
        print(f"\n{label} ({key[1]}): {', '.join(sorted(g))}")
        for k, it in g.items():
            fd = it["fieldData"]
            if it.get("isDraft"):
                print(f"  · {k}: overslaan (draft-status) {fd['slug']}"); continue
            block = build_block(g, k, label)
            patch = {}
            # blok staat in het eerste veld dat er al een heeft, anders in 'content'
            target = next((f for f in FIELDS if BLOCK_RE.search(fd.get(f) or "")), "content")
            new = place(fd.get(target), block)
            if new is None:
                print(f"  ! {k}: geen plek gevonden in {fd['slug']}"); continue
            if new != (fd.get(target) or ""):
                patch[target] = new
            if not patch:
                print(f"  = {k}: al actueel"); continue
            changed += 1
            if dry:
                print(f"  ○ {k}: zou bijwerken {fd['slug']}\n      {block}")
            else:
                WF.update_live(it["id"], patch)
                print(f"  ✔ {k}: bijgewerkt {fd['slug']}")
    print(f"\nKLAAR — {changed} artikel(en) {'zouden worden ' if dry else ''}bijgewerkt.")
    return changed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--days", type=float, default=3, help="wedstrijden t/m zoveel dagen vooruit")
    ap.add_argument("--back", type=float, default=6, help="en zoveel uur terug")
    ap.add_argument("--max", type=int, default=800, help="max. aantal recente nieuwsitems om te scannen")
    a = ap.parse_args()
    if not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt."); sys.exit(1)
    run(a.dry, a.days, a.back, a.max)

if __name__ == "__main__":
    main()
