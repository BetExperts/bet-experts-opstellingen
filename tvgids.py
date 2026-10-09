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
import re, urllib.request, html, difflib, unicodedata
from datetime import datetime

BASE = "https://waaroptv.nl"
START = BASE + "/sport/voetbal/"
UA = "Mozilla/5.0 (compatible; BetExpertsBot/1.0; +https://www.bet-experts.nl)"
MAX_PAGES = 6

# 'zenders' op waaroptv die eigenlijk een bookmaker-livestream zijn -> PROVIDERS-sleutel (of None)
BOOKMAKERS = {"bet365": "bet365", "toto sport": "toto", "toto": "toto", "711": "711", "starcasino": "starcasino",
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

def _split_zenders(raw):
    """'TOTO Sport · Ziggo Sport' / 'ESPN 1/2' / 'NPO 1, NPO Start' -> losse zenders.
    Een los nummer erft de naam van de vorige zender ('ESPN 1/2' -> 'ESPN 1', 'ESPN 2')."""
    out = []
    for z in raw:
        prev = None
        for part in re.split(r"\s*[·/,]\s*", z or ""):
            part = part.strip()
            if not part:
                continue
            if prev and re.fullmatch(r"\d+", part):
                base = re.sub(r"\s*\d+$", "", prev)
                part = f"{base} {part}" if base else part
            if part not in out:
                out.append(part)
            prev = part
    return out

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
        zenders = _split_zenders(html.unescape(z).strip()
                                 for z in re.findall(r'wedstrijd-meta__zender">([^<]+)<', li))
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

# ---------- reservebron: tweede tv-gids (open JSON) — alleen gebruikt als de hoofdgids geen zender heeft ----------
# Nooit als bron noemen in teksten.
EXTRA_URL = "https://voetbaloptv.com/wp-json/vtv/v1/wedstrijden"
_EXTRA_DROP = re.compile(r"^(?:espn watch|ziggo kanaal \d+|viaplaytv)$", re.I)

def _extra_zenders(raw):
    """'ESPN Extra, ESPN, ESPN Watch' -> ['ESPN 1']; 'Ziggo Sport 3' -> ['Ziggo Sport 3']."""
    out = []
    for z in (raw or "").split(","):
        z = html.unescape(z).strip()
        if not z or _EXTRA_DROP.match(z):
            continue
        if z.upper() == "ESPN":
            z = "ESPN 1"
        elif z.lower() == "ziggo sport":
            z = "Ziggo Sport 1"
        if z not in out:
            out.append(z)
    if any(re.fullmatch(r"ESPN [1-4]", z) for z in out):          # lineaire zender bekend -> app-kanaal weglaten
        out = [z for z in out if z != "ESPN Extra"]
    return out

def _parse_extra(data):
    from zoneinfo import ZoneInfo
    tz, cards = ZoneInfo("Europe/Amsterdam"), []
    for r in (data or {}).get("data") or []:
        try:
            d, m, y = map(int, r["datum"].split("-")); hh, mm = map(int, r["tijd"].split(":"))
            ko = datetime(y, m, d, hh, mm, tzinfo=tz)
        except Exception:
            continue
        zenders = _extra_zenders(r.get("alle_zenders") or r.get("hoofdzender"))
        tv = [z for z in zenders if z.lower() not in BOOKMAKERS]
        bm = [z for z in zenders if z.lower() in BOOKMAKERS]
        gratis = any(z.upper().startswith("NPO") or z == "ESPN 1" for z in tv)
        cards.append({"home": html.unescape(r.get("thuisteam") or ""), "away": html.unescape(r.get("uitteam") or ""),
                      "kickoff": ko, "competitie": r.get("competitie") or "", "zenders": zenders, "tv": tv,
                      "bookmakers": bm, "providers": [BOOKMAKERS[b.lower()] for b in bm if BOOKMAKERS[b.lower()]],
                      "gratis": gratis, "url": "", "bron": "extra"})
    return cards

class TvGids:
    def __init__(self):
        self.cards = None
        self.error = None
        self.extra = None

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

    def load_extra(self):
        if self.extra is not None:
            return self.extra
        self.extra = []
        try:
            import json as _json
            req = urllib.request.Request(EXTRA_URL, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                self.extra = _parse_extra(_json.loads(r.read().decode()))
        except Exception as e:
            self.error = (self.error or "") + f" | reservebron: {type(e).__name__}: {e}"
        return self.extra

    def _best(self, cards, home, away, kickoff, min_score):
        best, best_s = None, 0.0
        for c in cards:
            try:
                if abs((c["kickoff"] - kickoff).total_seconds()) > 15 * 60:
                    continue
            except TypeError:
                continue
            s = min(_sim(home, c["home"]), _sim(away, c["away"]))
            if s > best_s:
                best, best_s = c, s
        return best if best_s >= min_score else None

    def lookup(self, home, away, kickoff, min_score=0.6):
        """Hoofdgids eerst; heeft die geen (tv-)zender voor deze wedstrijd, dan de reservebron."""
        best = self._lookup_main(home, away, kickoff, min_score)
        if best and best.get("tv"):
            return best
        ex = self._best(self.load_extra(), home, away, kickoff, min_score)
        if not ex or not ex.get("tv"):
            return best
        if not best:
            return ex
        merged = dict(best)                       # bookmaker-streams van de hoofdgids behouden, zender uit de reserve
        merged.update({"tv": ex["tv"], "gratis": ex["gratis"], "zenders": best["zenders"] + ex["tv"], "bron": "extra"})
        return merged

    def _lookup_main(self, home, away, kickoff, min_score=0.6):
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
