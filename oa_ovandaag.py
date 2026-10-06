# -*- coding: utf-8 -*-
"""Vermoedelijke opstellingen van opstellingvandaag.nl (openbare wedstrijdpagina's, robots.txt staat het toe).
Volgens de site worden de verwachte elftallen elk uur bijgewerkt, ook op basis van persconferenties.

NOOIT als bron noemen in onze artikelen (gebruiker, 07-10-2026): de namen worden alleen als input gebruikt.

  predicted(namen_thuis, namen_uit, ymd) -> dict of None
      {"url", "home": {"formation", "names"[11]}, "away": {...}, "confirmed": False}

Werkwijze: wedstrijd-URL's uit sitemap-actueel.xml + de homepage (1x per run), zoeken op datum
('-dd-mm-yyyy/') en teamnamen; op de wedstrijdpagina staan per ploeg de formatie en de regel
'Vermoedelijke opstelling <ploeg>: naam, naam, …'. Beleefd: vaste User-Agent, pauze tussen verzoeken.
"""
import difflib, html, re, time, unicodedata, urllib.request
from datetime import datetime

BASE = "https://opstellingvandaag.nl"
UA = "BetExpertsBot/1.0 (+https://www.bet-experts.nl)"
PAUSE = 1.0
STOP = {"fc", "sc", "afc", "cf", "sv", "vv", "jc", "de", "1", "04", "05"}

_index = None
_pages = {}


def _fold(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def _get(url):
    if url in _pages:
        return _pages[url]
    time.sleep(PAUSE)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xml"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "replace")
    _pages[url] = txt
    return txt


def _urls():
    """Alle wedstrijd-URL's met een datum in de slug (1x per run)."""
    global _index
    if _index is None:
        found = set()
        for src in (BASE + "/sitemap-actueel.xml", BASE + "/"):
            try:
                found |= set(re.findall(r"https://opstellingvandaag\.nl/[a-z0-9-]+/[a-z0-9-]+-\d{2}-\d{2}-\d{4}/", _get(src)))
            except Exception as e:
                print(f"     · opstellingen-bron niet bereikbaar ({src}): {e}")
        _index = sorted(found)
    return _index


def _sim(namen, part):
    """Hoe goed past een van de teamnamen op een deel van de slug (0..1)."""
    best = 0.0
    p = set(part.split("-")) - STOP
    for n in namen:
        f = _fold(n)
        if not f:
            continue
        t = set(f.split("-")) - STOP
        if f == part or (t and t == p):
            return 1.0
        if t and p and (t <= p or p <= t):
            best = max(best, 0.9)
        best = max(best, difflib.SequenceMatcher(None, f, part).ratio())
    return best


def _parse(page):
    txt = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", page)
    txt = html.unescape(re.sub(r"<[^>]+>", "\n", txt))
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    flat = "\n".join(lines)
    if re.search(r"(?i)\b(officiële|bevestigde) opstelling", flat):
        confirmed = True
    else:
        confirmed = False
    # 'Vermoedelijke opstelling PSV:' gevolgd door naam, ',' , naam, …
    teams = []
    for i, l in enumerate(lines):
        m = re.match(r"(?i)vermoedelijke opstelling (.+?):$", l)
        if not m:
            continue
        names, j = [], i + 1
        while j < len(lines) and len(names) < 11:
            if lines[j] != ",":
                names.append(lines[j])
            j += 1
        teams.append((m.group(1), names))
    forms = [l for l in lines if re.fullmatch(r"\d-\d(?:-\d){1,3}", l)]
    return teams, forms, confirmed


def predicted(namen_thuis, namen_uit, ymd):
    """Vermoedelijke opstelling, of None. namen_* = lijst met mogelijke namen (NL-naam, API-naam)."""
    try:
        d = datetime.fromisoformat(ymd)
        stamp = f"-{d.day:02d}-{d.month:02d}-{d.year}/"
        best = (0.0, None)
        for url in _urls():
            if not url.endswith(stamp):
                continue
            slug = url.rstrip("/").rsplit("/", 1)[1][: -len(stamp) + 1]
            parts = slug.split("-")
            for k in range(1, len(parts)):
                sc = min(_sim(namen_thuis, "-".join(parts[:k])), _sim(namen_uit, "-".join(parts[k:])))
                if sc > best[0]:
                    best = (sc, url)
        if best[0] < 0.75:
            return None
        teams, forms, confirmed = _parse(_get(best[1]))
        if len(teams) < 2 or any(len(n) != 11 for _, n in teams[:2]):
            return None
        fh = forms[0] if len(forms) >= 2 else ""
        fa = forms[1] if len(forms) >= 2 else ""
        return {"url": best[1], "confirmed": confirmed,
                "home": {"formation": fh, "names": teams[0][1]},
                "away": {"formation": fa, "names": teams[1][1]}}
    except Exception as e:
        print(f"     · opstellingen-bron niet beschikbaar: {e}")
    return None


def as_lineup(side, url):
    """In het formaat van API-Football (startXI/player/name); source 'extern' = externe voorspelling."""
    return {"formation": side.get("formation") or "", "source": "extern", "source_url": url, "team": {},
            "startXI": [{"player": {"name": n}} for n in side["names"]]}
