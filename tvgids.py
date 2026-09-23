# -*- coding: utf-8 -*-
"""Tv-gids via waaroptv.nl/sport/voetbal/ — exacte zender per wedstrijd.

Leest de overzichtspagina('s) (gewone WordPress-HTML, robots.txt staat het toe), met
maximaal een paar verzoeken per run. Per wedstrijd: competitie, teams, aftrap
(ISO-tijd), zender(s) en of hij gratis te zien is. Bookmakers (bet365, TOTO Sport,
711) staan daar ook als 'zender' als ze de wedstrijd streamen; die houden we apart.

Faalt het ophalen (netwerk, Cloudflare), dan geeft lookup() gewoon None en valt de
agent terug op zijn eigen config. Dit bestand is identiek in de live-kijken- en
opstellingen-agent.
"""
import re, html, difflib, unicodedata, urllib.request
from datetime import datetime

BASE = "https://waaroptv.nl"
START = BASE + "/sport/voetbal/"
UA = "Mozilla/5.0 (compatible; BetExpertsBot/1.0; +https://www.bet-experts.nl)"
MAX_PAGES = 6

# 'zenders' op waaroptv die eigenlijk een bookmaker-livestream zijn -> PROVIDERS-sleutel (of None)
BOOKMAKERS = {"bet365": "bet365", "toto sport": "toto", "toto": "toto", "711": "711",
              "unibet": None, "betcity": None, "jacks": None, "betmgm": None, "circus": None,
              "holland casino": None, "leovegas": None, "vbet": None, "bingoal": None}

_STOP = {"fc", "sk", "sc", "cf", "ac", "as", "afc", "bk", "fk", "if", "cd", "rc", "ssc", "us",
         "sv", "vfb", "vfl", "tsg", "ss", "ud", "sd", "ca", "cs", "kv", "krc", "rsc", "club", "calcio"}

def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _STOP]
    return " ".join(toks)

def _sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb)
    return max(jac, difflib.SequenceMatcher(None, a, b).ratio())

def _get(url):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(r, timeout=25) as resp:
        return resp.read().decode("utf-8", "ignore")

def _parse(page):
    cards = []
    for li in re.findall(r'<li class="wp-block-post[^"]*".*?</li>', page, flags=re.S):
        naam = re.search(r'wedstrijd-card__naam"><a href="([^"]+)">([^<]+)</a>', li)
        tijd = re.search(r'<time datetime="([^"]+)"', li)
        if not naam or not tijd:
            continue
        teams = re.split(r"\s+[–-]\s+", html.unescape(naam.group(2)).strip(), maxsplit=1)
        if len(teams) != 2:
            continue
        comp = re.search(r'wedstrijd-card__competitie">([^<]+)<', li)
        zenders = [html.unescape(z).strip() for z in re.findall(r'wedstrijd-meta__zender">([^<]+)<', li)]
        try:
            ko = datetime.fromisoformat(tijd.group(1))
        except ValueError:
            continue
        tv = [z for z in zenders if z.lower() not in BOOKMAKERS]
        bm = [z for z in zenders if z.lower() in BOOKMAKERS]
        cards.append({"home": teams[0], "away": teams[1], "kickoff": ko,
                      "competitie": html.unescape(comp.group(1)).strip() if comp else "",
                      "zenders": zenders, "tv": tv, "bookmakers": bm,
                      "providers": [BOOKMAKERS[b.lower()] for b in bm if BOOKMAKERS[b.lower()]],
                      "gratis": "wedstrijd-meta__gratis" in li, "url": naam.group(1)})
    return cards

class TvGids:
    def __init__(self):
        self.cards = None
        self.error = None

    def load(self):
        if self.cards is not None:
            return self.cards
        self.cards, url = [], START
        try:
            for _ in range(MAX_PAGES):
                page = _get(url)
                self.cards += _parse(page)
                nxt = re.search(r'<a href="([^"]+)" class="wp-block-query-pagination-next"', page)
                if not nxt:
                    break
                url = nxt.group(1) if nxt.group(1).startswith("http") else BASE + html.unescape(nxt.group(1))
        except Exception as e:           # netwerk/Cloudflare: agent valt terug op eigen config
            self.error = f"{type(e).__name__}: {e}"
        return self.cards

    def lookup(self, home, away, kickoff, min_score=0.6):
        """Beste kaart voor deze wedstrijd (zelfde aftrap ±15 min, teamnamen lijken), of None."""
        best, best_s = None, 0.0
        for c in self.load():
            try:
                if abs((c["kickoff"] - kickoff).total_seconds()) > 15 * 60:
                    continue
            except TypeError:
                continue
            s = min(_sim(home, c["home"]), _sim(away, c["away"]))
            if s > best_s:
                best, best_s = c, s
        return best if best_s >= min_score else None

def tv_label(card):
    """'Ziggo Sport 1', 'NPO 3' of 'ESPN 1 en ESPN 2' (alleen echte tv-zenders)."""
    tv = (card or {}).get("tv") or []
    return " en ".join(tv) if tv else None
