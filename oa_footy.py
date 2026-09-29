# -*- coding: utf-8 -*-
"""Vermoedelijke opstellingen van FootyMetrics (footymetrics.com) — met toestemming van de eigenaar.

Er is geen feed/API-sleutel; we lezen de openbare wedstrijdpagina (robots.txt staat /fixtures/ en
/teams/ toe, /api/ NIET — die gebruiken we dus ook niet).

  predicted(home_api_name, away_api_name, ymd) -> dict of None
      {"url", "home": {"formation", "names"[11]}, "away": {...}, "confirmed": bool}

Werkwijze: teampagina van de thuisploeg (via sitemap/teams.xml) -> link naar de wedstrijd met de
uitploeg -> wedstrijdpagina: formaties uit de paginadata, de elf namen uit de FAQ (JSON-LD).
Beleefd: vaste User-Agent, pauze tussen verzoeken, teamlijst 1x per run.
"""
import difflib, html, json, re, time, unicodedata, urllib.request
from datetime import datetime, timedelta

BASE = "https://www.footymetrics.com"
UA = "BetExpertsBot/1.0 (+https://www.bet-experts.nl; opstellingen, met toestemming)"
PAUSE = 1.0

# API-Football-naam (geslugd) -> FootyMetrics-teamslug, waar ze afwijken
ALIAS = {
    "czechia": "czech-republic", "fyr-macedonia": "north-macedonia", "rep-of-ireland": "republic-of-ireland",
    "bosnia-herzegovina": "bosnia-and-herzegovina", "bosnia-and-herzegovina": "bosnia-and-herzegovina",
    "turkey": "turkiye", "usa": "usa", "psv-eindhoven": "psv", "az-alkmaar": "az-alkmaar",
}

_teams = None
_pages = {}

def _slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
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

def _team_index():
    """{teamslug: '/teams/<id>-<slug>'} uit de sitemap (1x per run)."""
    global _teams
    if _teams is None:
        _teams = {}
        try:
            xml = _get(BASE + "/sitemap/teams.xml")
            for path in re.findall(r"<loc>https://www\.footymetrics\.com(/teams/\d+-([a-z0-9-]+))</loc>", xml):
                _teams.setdefault(path[1], path[0])
        except Exception as e:
            print(f"     · FootyMetrics teamlijst niet op te halen: {e}")
    return _teams

def _candidates(api_name, n=3):
    idx = _team_index()
    s = _slug(api_name)
    s = ALIAS.get(s, s)
    if s in idx:
        return [s]
    # jeugd-/vrouwenteams alleen als de API-naam er zelf een is
    youth = re.compile(r"(^|-)(jong|women|w|u1\d|u2\d|vrouwen|ii|b)(-|$)")
    pool = [x for x in idx if bool(youth.search(x)) == bool(youth.search(s))]
    # 'FC Twente' -> 'fc-twente' / 'twente'
    out = [x for x in (s.replace("fc-", ""), s + "-fc", "fc-" + s) if x in idx]
    # 'Roda' -> 'roda-jc-kerkrade', 'Heracles' -> 'heracles-almelo' (alle woorden aanwezig, zelfde begin)
    toks = set(s.split("-")) - {"fc", "sc", "afc", "cf"}
    out += sorted((x for x in pool if toks and toks <= set(x.split("-")) and x.split("-")[0] == s.split("-")[0]
                   and x not in out), key=len)[:n]
    return out + [x for x in difflib.get_close_matches(s, pool, n=n, cutoff=0.8) if x not in out]

def _parse_fixture(page):
    t = page.replace('\\"', '"')
    m = re.search(r'"lineupPredicted":(true|false),"lineupConfirmed":(true|false),'
                  r'"homeFormation":("[^"]*"|null),"awayFormation":("[^"]*"|null)', t)
    ts = re.search(r'"timestamp":"\$D([0-9T:\-\.]+)Z?"', t)
    hn = re.search(r'"Home":\{"apid":\d+,"name":"([^"]+)"', t)
    an = re.search(r'"Away":\{"apid":\d+,"name":"([^"]+)"', t)
    if not (m and hn and an):
        return None
    lineups = {}
    for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            d = json.loads(blob)
        except Exception:
            continue
        for q in (d.get("mainEntity") or []) if isinstance(d, dict) else []:
            txt = html.unescape(((q.get("acceptedAnswer") or {}).get("text")) or "")
            mm = re.match(r"(.+?)'s (predicted|confirmed) lineup is: (.+?)\.?$", txt)
            if mm:
                names = [x.strip() for x in mm.group(3).split(",") if x.strip()]
                lineups[mm.group(1).strip()] = names
    fm = lambda v: None if v == "null" else v.strip('"')
    return {
        "predicted": m.group(1) == "true", "confirmed": m.group(2) == "true",
        "home_formation": fm(m.group(3)), "away_formation": fm(m.group(4)),
        "kickoff": ts.group(1) if ts else None,
        "home_name": hn.group(1), "away_name": an.group(1),
        "home_xi": lineups.get(hn.group(1)), "away_xi": lineups.get(an.group(1)),
    }

def predicted(home_api_name, away_api_name, ymd):
    """Vermoedelijke opstelling voor deze wedstrijd, of None (dan valt de agent terug op eigen methode)."""
    try:
        homes, aways = _candidates(home_api_name), _candidates(away_api_name)
        if not homes or not aways:
            return None
        idx = _team_index()
        for hs in homes:
            links = sorted(set(re.findall(r'/fixtures/\d+-[a-z0-9-]+', _get(BASE + idx[hs]))), reverse=True)
            for link in links:
                if not any(link.endswith(f"-{hs}-{a}") for a in aways):
                    continue
                url = BASE + link
                p = _parse_fixture(_get(url))
                if not p or not p.get("kickoff"):
                    continue
                ko = datetime.fromisoformat(p["kickoff"].split(".")[0])
                if abs((ko.date() - datetime.fromisoformat(ymd).date()).days) > 1:
                    continue          # andere ontmoeting tussen dezelfde ploegen
                hx, ax = p.get("home_xi") or [], p.get("away_xi") or []
                if len(hx) != 11 or len(ax) != 11:
                    return None
                return {"url": url, "confirmed": p["confirmed"],
                        "home": {"formation": p["home_formation"], "names": hx},
                        "away": {"formation": p["away_formation"], "names": ax}}
    except Exception as e:
        print(f"     · FootyMetrics niet beschikbaar: {e}")
    return None

def as_lineup(side, url):
    """In het formaat van API-Football (startXI/player/name) zodat de rest van de agent het snapt."""
    return {"formation": side.get("formation") or "", "source": "footymetrics", "source_url": url,
            "startXI": [{"player": {"name": n}} for n in side["names"]]}
