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
# 28-10-2026 (Jasper): NIET MEER GEBRUIKEN. Hun voorwaarden (art. 4.3) verbieden het periodiek verzamelen van opstellingen
# en afwezigen en het herpubliceren daarvan, en in hun afwezigenblok stond spam die in onze voorbeschouwingen kwam.
# Alle functies geven None; de agents vallen terug op FootyMetrics en API-Football. Niet weer aanzetten.
UIT = True
UA = "BetExpertsBot/1.0 (+https://www.bet-experts.nl)"
PAUSE = 1.0
STOP = {"fc", "sc", "afc", "cf", "sv", "vv", "jc", "de", "1", "04", "05"}

_index = None
_pages = {}


def _fold(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def _get(url):
    if UIT:
        raise RuntimeError("opstellingvandaag.nl staat uit (voorwaarden art. 4.3)")
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


# Afkortingen/andere namen die de bron in de URL gebruikt (20-10-2026: PSG–Barcelona werd niet gevonden)
ALIASSEN = {"paris-saint-germain": ["psg", "paris-sg"], "paris-saint-germain-fc": ["psg"], "paris-sg": ["psg"],
            "manchester-united": ["man-utd", "man-united"], "manchester-city": ["man-city"],
            "tottenham-hotspur": ["tottenham", "spurs"], "tottenham": ["spurs"], "wolverhampton-wanderers": ["wolves"], "wolves": ["wolverhampton"],
            "borussia-monchengladbach": ["gladbach", "monchengladbach"], "borussia-dortmund": ["dortmund", "bvb"],
            "bayern-munchen": ["bayern", "bayern-munchen"], "bayern-munich": ["bayern", "bayern-munchen"],
            "athletic-club": ["athletic-bilbao", "bilbao"], "atletico-madrid": ["atletico"], "sporting-cp": ["sporting", "sporting-lissabon"],
            "fc-copenhagen": ["fc-kopenhagen", "kopenhagen"], "inter": ["inter-milan", "internazionale"], "az-alkmaar": ["az"],
            "olympiakos-piraeus": ["olympiacos", "olympiakos"], "fk-crvena-zvezda": ["rode-ster-belgrado", "crvena-zvezda"],
            "union-st-gilloise": ["union-sint-gillis", "union-sg"], "st-truiden": ["sint-truiden", "stvv"],
            "stade-brestois-29": ["brest"], "heart-of-midlothian": ["hearts"], "rb-leipzig": ["leipzig"], "bayer-leverkusen": ["leverkusen"]}


def _met_aliassen(namen):
    uit = list(namen)
    for n in namen:
        uit += [a for a in ALIASSEN.get(_fold(n), []) if a not in uit]
    return uit


def _sim(namen, part):
    """Hoe goed past een van de teamnamen op een deel van de slug (0..1)."""
    best = 0.0
    namen = _met_aliassen(namen)
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
        # vóór de bekendmaking 'Vermoedelijke opstelling PSV:', daarna 'Opstelling PSV:' (bevestigd)
        m = re.match(r"(?i)(?:vermoedelijke )?opstelling (.+?):$", l)
        if not m:
            continue
        names, j = [], i + 1
        while j < len(lines) and len(names) < 11:
            # meestal één naam per regel, soms de hele elf als 'naam, naam, …' in één regel
            names += [n.strip() for n in lines[j].split(",") if n.strip()]
            j += 1
        names = names[:11]
        teams.append((m.group(1), names))
    forms = [l for l in lines if re.fullmatch(r"\d-\d(?:-\d){1,3}", l)]
    return teams, forms, confirmed


def match_url(namen_thuis, namen_uit, ymd):
    """URL van de wedstrijdpagina (of None)."""
    if UIT:
        return None
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
        return best[1] if best[0] >= 0.75 else None
    except Exception as e:
        print(f"     · opstellingen-bron niet beschikbaar: {e}")
    return None


def absences(namen_thuis, namen_uit, ymd, url=None):
    """Afwezigen per ploeg uit het blok 'Blessures en schorsingen':
    {"home": [(naam, reden, status)], "away": [...]} — een lege lijst = 'Iedereen inzetbaar';
    een ploeg die niet in het blok staat ontbreekt in de dict. None als de pagina/het blok ontbreekt."""
    if UIT:
        return None
    try:
        url = url or match_url(namen_thuis, namen_uit, ymd)
        if not url:
            return None
        txt = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", _get(url))
        lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", txt)).split("\n") if l.strip()]
        if "Blessures en schorsingen" not in lines:
            return None
        i = lines.index("Blessures en schorsingen") + 1
        out, team, buf = {}, None, []
        def flush():
            if team:
                out[team] = [tuple(buf[k:k + 3]) for k in range(0, len(buf) - 2, 3)]
        while i < len(lines):
            l = lines[i]; i += 1
            if l.endswith("?") or l == "Spelers om op te letten":
                break
            kant = "home" if _sim(namen_thuis, _fold(l)) >= 0.85 else "away" if _sim(namen_uit, _fold(l)) >= 0.85 else None
            if kant and kant not in out and kant != team:
                flush(); team, buf = kant, []
                continue
            if l.rstrip(".").lower() == "iedereen inzetbaar":
                continue
            buf.append(l)
        flush()
        if not schoon(out):
            print(f"     ⚠ afwezigen-bron afgewezen (verdachte tekst): {url}")
            return None
        return out or None
    except Exception as e:
        print(f"     · afwezigen-bron niet beschikbaar: {e}")
    return None


# 28-10-2026: in het afwezigenblok van de externe bron stond spam (reclame voor medicijnen met onze naam erin), die
# zo in de voorbeschouwingen terechtkwam. Daarom alleen nog korte, 'gewone' regels: een naam (letters, max 5 woorden),
# een korte reden en status. Eén afwijkende regel = het hele blok weg (de bron is dan niet te vertrouwen).
SPAM = re.compile(r"oxy|contin|norm\b|kopen|koop|bestel|discreet|klik|hier\b|veilig|bet.?experts|mg\b|pil|recept|apothe|"
                  r"viagra|cialis|xanax|tramadol|codein|casino|bonus|gratis|http|www|\.nl|\.com|@", re.I)
NAAM = re.compile(r"^[^\W\d_][\w'’. \-]{1,38}$")


def schoon(out):
    for lijst in (out or {}).values():
        for t in lijst:
            if len(t) != 3:
                return False
            naam, reden, status = t
            if not NAAM.match(naam) or len(naam.split()) > 5 or any(ch.isdigit() for ch in naam):
                return False
            if len(reden) > 40 or len(status) > 30:
                return False
            if SPAM.search(" ".join(t)):
                return False
    return True


def predicted(namen_thuis, namen_uit, ymd):
    """Vermoedelijke opstelling, of None. namen_* = lijst met mogelijke namen (NL-naam, API-naam)."""
    if UIT:
        return None
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
