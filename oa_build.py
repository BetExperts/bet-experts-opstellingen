# -*- coding: utf-8 -*-
"""Bouwt titel, samenvatting en de 3 rich-text content-delen voor een
opstellingen-artikel. Alleen Webflow-compatibele HTML: <p> <h3> <ul> <li>
<strong> <br> <a>. GEEN tabellen."""
import random, html, re, unicodedata
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    TZ = None
from oa_config import club_slug, reason_nl, HUB_PATH, nl_name

DAGEN = ["maandag","dinsdag","woensdag","donderdag","vrijdag","zaterdag","zondag"]
MAAND = ["januari","februari","maart","april","mei","juni","juli","augustus",
         "september","oktober","november","december"]
TELWOORD = {1: "één", 2: "twee", 3: "drie", 4: "vier", 5: "vijf"}

def _local(dt_iso):
    dt = datetime.fromisoformat(dt_iso.replace("Z","+00:00"))
    if TZ: dt = dt.astimezone(TZ)
    return dt

def nl_datum(dt): return f"{DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]} {dt.year}"
def nl_tijd(dt):  return f"{dt.hour:02d}:{dt.minute:02d}"
def esc(s): return html.escape(str(s or ""), quote=False)

# ---------- datum/tijd (incl. nachtwedstrijden) ----------
def is_nacht(dt):
    """Aftrap tussen 00:00 en 05:00 -> 'in de nacht van ... op ...'."""
    return 0 <= dt.hour < 5

def nacht_label(dt, weekdag=True, jaar=True):
    """'nacht van zaterdag 3 op zondag 4 oktober 2026' (maand/jaar van de vorige dag alleen als ze verschillen)."""
    v = dt - timedelta(days=1)
    d1 = f"{DAGEN[v.weekday()]} {v.day}" if weekdag else f"{v.day}"
    if v.month != dt.month: d1 += f" {MAAND[v.month-1]}"
    if v.year != dt.year and jaar: d1 += f" {v.year}"
    d2 = f"{DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]}" if weekdag else f"{dt.day} {MAAND[dt.month-1]}"
    if jaar: d2 += f" {dt.year}"
    return f"nacht van {d1} op {d2}"

def datum_label(dt):
    """Voor het infoblok: 'zaterdag 3 oktober 2026' of 'nacht van zaterdag 3 op zondag 4 oktober 2026'."""
    return nacht_label(dt) if is_nacht(dt) else nl_datum(dt)

def moment(dt):
    """'op zaterdag 3 oktober 2026 om 15:00 uur' / 'in de nacht van zaterdag 3 op zondag 4 oktober 2026 om 02:00 uur'."""
    if is_nacht(dt):
        return f"in de {nacht_label(dt)} om {nl_tijd(dt)} uur"
    return f"op {nl_datum(dt)} om {nl_tijd(dt)} uur"

def cap(s): return s[:1].upper() + s[1:] if s else s

# ---------- landnamen met lidwoord ----------
# meervoudige landnamen ('de Verenigde Staten zijn') en enkelvoudige met 'de' ('de Dominicaanse Republiek is')
_MV_RE = re.compile(r"(eilanden|Staten|Faeröer|Bahama's|Filipijnen|Seychellen|Comoren|Emiraten|Malediven|Antillen|Grenadines)$")
_DE_RE = re.compile(r"(Republiek)$")

def meervoud(team):
    t = (team or "").strip()
    return bool(_MV_RE.search(t)) and not t.startswith("Jong ")

def de(team):
    """Teamnaam zoals hij in een lopende zin hoort: 'de Faeröer', 'de Dominicaanse Republiek', 'Nederland'."""
    t = (team or "").strip()
    if t.startswith("Jong "):
        return t
    return f"de {t}" if (_MV_RE.search(t) or _DE_RE.search(t)) else t

def De(team): return cap(de(team))

def ww(team, ev, mv):
    """Werkwoordsvorm die past bij de teamnaam: ww('Verenigde Staten', 'speelt', 'spelen') -> 'spelen'."""
    return mv if meervoud(team) else ev

def _lidwoord_prefix(team):
    """'de ' als de teamnaam een lidwoord krijgt (voor vóór een link), anders ''."""
    return de(team)[:-len(team)] if team and de(team) != team else ""

# ---------- stadion ----------
def stadion_met_lidwoord(name):
    """'het Philips Stadion', 'de Puskás Aréna', 'Stadion Galgenwaard', 'De Kuip', 'Parken'."""
    n = (name or "").strip()
    if not n: return ""
    words = [w.lower() for w in re.split(r"[\s\-]+", n)]
    if words[0] in ("de", "het"):
        return n
    if words[0] in ("stadion", "stadiumi", "stadionul"):
        return n
    if (set(words) & {"stadion", "stadium", "stade", "estádio", "estadio", "stadio", "stadyumu"}
            or words[-1].endswith("stadion")):
        return "het " + n
    if set(words) & {"arena", "aréna"} or words[-1].endswith(("arena", "dome")):
        return "de " + n
    return n

def _stad_in_naam(city, venue):
    k = lambda x: re.sub(r"[^a-z0-9]", "", _fold(x))
    return bool(city) and k(city) in k(venue)

def plek_tekst(venue, city):
    """'het Koning Boudewijnstadion (Brussel)' / 'Helsinki' / ''. Stad niet herhalen als die al in de naam staat."""
    if venue:
        s = stadion_met_lidwoord(venue)
        if city and not _stad_in_naam(city, venue):
            s += f" ({city})"
        return s
    return city or ""

# ---------- opstelling-regel ----------
def _players(lu):
    return lu.get("startXI") or []

_GRID_RE = re.compile(r"^\d+:\d+$")

def xi_line(lu):
    """Spelers per linie, linies gescheiden door ';' (keeper; verdediging; middenveld; aanval).
    1) API-grid ('rij:kolom') als élke speler er een heeft;
    2) anders de bronvolgorde (keeper eerst), gesplitst volgens de formatie als die klopt (4-3-3 -> 1;4;3;3);
    3) anders gewoon de bronvolgorde."""
    pls = [pp.get("player") or {} for pp in _players(lu)]
    pls = [p for p in pls if p.get("name")]
    if not pls:
        return ""
    if all(_GRID_RE.match(str(p.get("grid") or "")) for p in pls):
        rows = {}
        for p in pls:
            r, c = (int(x) for x in p["grid"].split(":"))
            rows.setdefault(r, []).append((c, p["name"]))
        return "; ".join(", ".join(esc(n) for _, n in sorted(rows[r])) for r in sorted(rows))
    # keeper vooraan (als de bron posities meegeeft), verder de volgorde van de bron
    pls = sorted(pls, key=lambda p: 0 if (p.get("pos") or "").upper() == "G" else 1)
    names = [p["name"] for p in pls]
    f = formation(lu)
    if re.fullmatch(r"\d+(-\d+)+", f or "") and len(names) == 11 and sum(int(x) for x in f.split("-")) == 10:
        parts, i = [], 0
        for k in [1] + [int(x) for x in f.split("-")]:
            parts.append(", ".join(esc(n) for n in names[i:i+k])); i += k
        return "; ".join(parts)
    return ", ".join(esc(n) for n in names)

def formation(lu): return (lu or {}).get("formation") or ""

def _xi_names(lu):
    return set((pp.get("player") or {}).get("name","") for pp in _players(lu))

# letters die NFKD niet ontleedt ('Mütəllimov' ~ 'Mütallimov', 'Ødegaard' ~ 'Odegaard')
_FOLD_TR = str.maketrans({"ə": "a", "Ə": "a", "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l",
                          "đ": "d", "Đ": "d", "ß": "ss", "æ": "ae", "Æ": "ae", "ð": "d", "þ": "th"})

def _fold(x):
    return unicodedata.normalize("NFKD", (x or "").translate(_FOLD_TR)).encode("ascii", "ignore").decode().lower().strip()

def rotation_note(last, prev, team, absent=None):
    """Detecteert wisselingen tussen de laatste twee opstellingen -> positiestrijd-zin.
    Spelers die nu geblesseerd/geschorst zijn tellen niet mee als 'concurrent'."""
    if not last or not prev: return ""
    a, b = _xi_names(last), _xi_names(prev)
    absent = {_fold(x) for x in (absent or set()) if x}
    nieuw = [n for n in a - b if n]
    weg_absent = [n for n in b - a if n and _fold(n) in absent]
    eruit = [n for n in b - a if n and _fold(n) not in absent]
    if len(nieuw) == 1 and not eruit and weg_absent:
        return (f"Bij {de(team)} lijkt <strong>{esc(nieuw[0])}</strong> zijn plek te houden, want "
                f"<strong>{esc(weg_absent[0])}</strong> ontbreekt door een blessure of schorsing.")
    if not nieuw:
        return (f"{De(team)} {ww(team, 'koos', 'kozen')} in de laatste twee wedstrijden vrijwel dezelfde basiself, "
                f"dus veel verrassingen zijn niet te verwachten.")
    if len(nieuw) == 1 and len(eruit) == 1:
        return (f"De grootste vraag bij {de(team)} is de strijd om één basisplaats: waar in het laatste duel "
                f"<strong>{esc(nieuw[0])}</strong> startte, kreeg een wedstrijd eerder <strong>{esc(eruit[0])}</strong> de voorkeur. "
                f"Die positiestrijd is dé keuze waar de trainer vlak voor aftrap knopen over doorhakt.")
    return (f"{De(team)} {ww(team, 'roteerde', 'roteerden')} de laatste wedstrijden op enkele posities "
            f"(o.a. {esc(', '.join(nieuw[:3]))}). De definitieve keuzes worden vlak voor aftrap duidelijk.")

# ---------- blessures ----------
def _same_player(inj_pl, xi_pls):
    """Zelfde speler? Op id, anders op naam ('S. Ouaissa' ~ 'Sami Ouaissa': achternaam + eerste letter)."""
    pid = inj_pl.get("id")
    if pid and any(pid == p.get("id") for p in xi_pls):
        return True
    n = _fold(inj_pl.get("name")).replace(".", " ").split()
    if not n: return False
    for p in xi_pls:
        m = _fold(p.get("name")).replace(".", " ").split()
        if not m: continue
        if n == m or (n[-1] == m[-1] and n[0][:1] == m[0][:1]):
            return True
    return False

def injuries_sentence(team, inj_list, xi=None):
    """-> (html, aantal). Spelers die in 'xi' (de getoonde basiself) staan, worden weggelaten."""
    xi_pls = [pp.get("player") or {} for pp in ((xi or {}).get("startXI") or [])]
    seen, out = set(), []
    for i in (inj_list or []):
        pl = i.get("player") or {}
        nm = pl.get("name")
        if not nm or nm in seen or _same_player(pl, xi_pls):
            continue
        seen.add(nm)
        reden = reason_nl(pl.get("reason"))
        if (pl.get("type") or "").lower() == "questionable":
            reden += ", twijfelachtig"
        out.append(f"{esc(nm)} ({esc(reden)})")
    if not out:
        return f"<strong>{esc(team)}:</strong> geen afwezigen gemeld.", 0
    out = out[:8]
    return f"<strong>{esc(team)}:</strong> " + ", ".join(out) + (" ontbreekt." if len(out) == 1 else " ontbreken."), len(out)

# ---------- titel + samenvatting ----------
TITLE_MAX = 70

def _hooks(homeN, awayN, pH, pA, has_pred=True, definitief=False):
    """Mogelijke titel-hooks (Nederlands, zonder (Engelse) stadsnamen)."""
    if not has_pred:
        if definitief:
            return ["de basisploegen zijn bekend",
                    "zo starten beide ploegen",
                    "de officiële elftallen op een rij",
                    "dit zijn de basisspelers",
                    "de trainers hebben gekozen",
                    "wie staat er in de basis?"]
        return ["wie start er in de basis?",
                "dit zijn de verwachte namen",
                "de vermoedelijke elftallen op een rij",
                "wie krijgt de voorkeur?",
                "zo verschijnen beide ploegen aan de aftrap",
                "het verwachte teamnieuws",
                "de basiself onder de loep",
                "wie krijgt een basisplaats?"]
    fav, und, favp = (homeN, awayN, pH) if pH >= pA else (awayN, homeN, pA)
    F, U = de(fav), de(und)
    if abs(pH-pA) <= 12:
        return ["een gelijkopgaand duel",
                f"{de(homeN)} en {de(awayN)} aan elkaar gewaagd",
                "alles kan in dit duel",
                "een spannende clash op komst",
                "wie trekt aan het langste eind?",
                "de krachten in evenwicht"]
    if favp >= 65:
        return [f"{F} torenhoog favoriet",
                f"{F} de gedoodverfde favoriet",
                f"{F} {ww(fav, 'moet', 'moeten')} het karwei klaren",
                f"{F} {ww(fav, 'jaagt', 'jagen')} op de volle buit",
                f"{ww(und, 'kan', 'kunnen')} {U} verrassen?",
                f"{F} {ww(fav, 'is', 'zijn')} de grote favoriet"]
    return [f"{F} licht favoriet",
            f"{F} favoriet, maar {U} {ww(und, 'loert', 'loeren')}",
            f"{F} aan zet",
            f"{F} met de beste papieren",
            f"{F} {ww(fav, 'start', 'starten')} als favoriet",
            f"{ww(und, 'loert', 'loeren')} {U} op een stunt?"]

def build_title(definitief, homeN, awayN, city, pH, pA, has_pred=True):
    """'Vermoedelijke opstelling X – Y | Hook'. De hook valt weg als de titel daardoor te lang wordt
    (de kerninformatie, soort + teams, blijft altijd staan)."""
    kind = "Definitieve opstelling" if definitief else "Vermoedelijke opstelling"
    base = f"{kind} {homeN} – {awayN}"
    hooks = _hooks(homeN, awayN, pH, pA, has_pred, definitief)
    pick = random.choice(hooks)                     # deterministisch via seed per wedstrijd
    if len(base) + 3 + len(pick) > TITLE_MAX:
        fits = [h for h in hooks if len(base) + 3 + len(h) <= TITLE_MAX]
        if not fits:
            return base
        pick = random.choice(fits)
    return f"{base} | {cap(pick)}"

META_MAX = 155

def build_samenvatting(definitief, homeN, awayN, comp, dt, has_pred=True):
    """Meta-omschrijving van max. META_MAX tekens: kies de langste variant die past."""
    kind = "Definitieve" if definitief else "Vermoedelijke"
    soort = "bevestigde" if definitief else "verwachte"
    tijd = nl_tijd(dt)
    if is_nacht(dt):
        whens = [f"{nacht_label(dt, jaar=False)}, {tijd} uur", nacht_label(dt, weekdag=False, jaar=False)]
    else:
        whens = [f"{DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]}, {tijd} uur",
                 f"{DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]}",
                 f"{dt.day} {MAAND[dt.month-1]}"]
    lijst = "blessures, vorm en winkansen" if has_pred else "blessures en vorm"
    tails = [f"bekijk de {soort} basiselftallen, {lijst}.",
             f"{soort} basiselftallen, {lijst}.",
             f"{soort} basiselftallen, blessures en vorm.",
             f"{soort} basiselftallen en blessures."]
    for tail in tails:
        for when in whens:
            s = f"{kind} opstellingen {homeN} – {awayN} ({comp}, {when}): {tail}"
            if len(s) <= META_MAX:
                return s
    s = f"{kind} opstellingen {homeN} – {awayN} ({comp})."
    return s if len(s) <= META_MAX else s[:META_MAX].rsplit(" ", 1)[0]

def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()   # ë -> e
    return re.sub(r"-+","-", re.sub(r"[^a-z0-9]+","-", s.lower())).strip("-")

def build_slug(home_slug, away_slug, dt):
    return f"opstelling-{home_slug}-{away_slug}-{dt.day:02d}-{dt.month:02d}-{dt.year}"

# ---------- content-delen ----------
def build_content(ctx):
    """ctx bevat alle opgehaalde data. Retourneert (content, content2, content3)."""
    homeN, awayN = ctx["homeN"], ctx["awayN"]
    hSlug, aSlug = ctx["hSlug"], ctx["aSlug"]
    compSlug, compN = ctx["compSlug"], ctx["compN"]
    dt = ctx["dt"]; city = ctx["city"]; venue = ctx["venue"]; ronde = ctx["ronde"]
    ronde_txt = ctx.get("ronde_txt") or f"Speelronde {ronde}"
    ronde_intro = ctx.get("ronde_intro") or f"speelronde {ronde}"
    definitief = ctx["definitief"]
    pH,pD,pA = ctx["pH"],ctx["pD"],ctx["pA"]
    has_pred = ctx.get("has_pred", True)
    hForm,aForm = ctx["hForm"], ctx["aForm"]
    hLU,aLU = ctx["hLU"], ctx["aLU"]              # laatste opstelling (predicted) of bevestigd
    hPrev,aPrev = ctx["hPrev"], ctx["aPrev"]      # vorige opstelling (voor rotatie)
    hInj,aInj = ctx["hInj"], ctx["aInj"]
    h2h = ctx["h2h"]
    kickoff = nl_tijd(dt)
    flip_dt = dt - timedelta(hours=1)
    flip = nl_tijd(flip_dt)

    def clublink(slug, name):
        inner = f'<a href="/clubs/{slug}">{esc(name)}</a>' if slug else f"<strong>{esc(name)}</strong>"
        return _lidwoord_prefix(name) + inner
    hLink = clublink(hSlug, homeN); aLink = clublink(aSlug, awayN)
    compLink = f'<a href="/competities/{compSlug}">{esc(compN)}</a>' if compSlug else f"<strong>{esc(compN)}</strong>"

    kop = "bevestigde" if definitief else "vermoedelijke"
    tv_kort, tv_faq = tv_info(ctx.get("tvgids"), homeN, awayN)

    # ---- CONTENT (deel 1/3): intro + info + thuisploeg-opstelling ----
    c1 = []
    c1.append(f'<p><a href="{HUB_PATH}">‹ Alle opstellingen</a></p>')
    plek = plek_tekst(venue, city)    # bij interlands levert de API vaak geen stadion
    waar = f" in {esc(plek)}" if plek else ""
    comp_deel = (f"in een {compLink}" if ctx.get("vriendschappelijk")
                 else f"in de {compLink}" if ctx.get("geen_ronde") else f"in {ronde_intro} van de {compLink}")
    onderdelen = ("de blessures en schorsingen, de recente vorm, de onderlinge duels en de winkansen "
                  "volgens de statistische voorspelling" if has_pred else
                  "de blessures en schorsingen, de recente vorm en de onderlinge duels")
    c1.append(f"<p><strong>{cap(moment(dt))} {ww(homeN, 'ontvangt', 'ontvangen')} {hLink} {aLink}{waar}, {comp_deel}. "
              f"Hieronder vind je de {kop} opstellingen van beide ploegen, {onderdelen}.</strong></p>")
    c1.append("<h3>Wedstrijdinformatie</h3>")
    stadion_regel = ""
    if venue:
        stadion_regel = f"<br><strong>Stadion:</strong> {esc(venue)}" + (f" ({esc(city)})" if city and not _stad_in_naam(city, venue) else "")
    elif city:
        stadion_regel = f"<br><strong>Plaats:</strong> {esc(city)}"
    c1.append(f"<p><strong>Wedstrijd:</strong> {esc(homeN)} – {esc(awayN)}<br>"
              + (f"<strong>Competitie:</strong> {esc(compN[:1].upper() + compN[1:])}<br>" if ctx.get("vriendschappelijk") or ctx.get("geen_ronde")
                 else f"<strong>Competitie:</strong> {esc(compN)} – {esc(ronde_txt)}<br>")
              + f"<strong>Datum:</strong> {datum_label(dt)}<br>"
              f"<strong>Aanvangstijd:</strong> {kickoff} uur"
              + stadion_regel
              + (f"<br><strong>{tv_kort[0]}:</strong> {esc(tv_kort[1])}" if tv_kort else "")
              + "</p>")
    # thuisploeg opstelling
    c1.append(_lineup_block(homeN, hLU, hPrev, definitief, kickoff, flip, is_home=True, absent={(i.get('player') or {}).get('name','') for i in (hInj or [])}))
    content = "\n".join(c1)

    # ---- CONTENT-2 (deel 2/3): uitploeg-opstelling + blessures + vorm ----
    c2 = []
    c2.append(_lineup_block(awayN, aLU, aPrev, definitief, kickoff, flip, is_home=False, absent={(i.get('player') or {}).get('name','') for i in (aInj or [])}))
    c2.append("<h3>Blessures &amp; schorsingen</h3>")
    # spelers die in de getoonde elf staan zijn er kennelijk wél bij -> niet als afwezig noemen
    # (bij de definitieve opstelling en bij de FootyMetrics-voorspelling, die blessures al meeweegt)
    def _xi_filter(lu):
        return lu if lu and (definitief or lu.get("source") in EXTERN) else None
    hTxt, hN = injuries_sentence(homeN, hInj, _xi_filter(hLU))
    aTxt, aN = injuries_sentence(awayN, aInj, _xi_filter(aLU))
    if hN or aN:
        c2.append("<p>Deze spelers ontbreken:</p>" if definitief else
                  "<p>De trainers moeten rekening houden met de volgende afwezigen:</p>")
        c2.append("<ul><li>"+hTxt+"</li><li>"+aTxt+"</li></ul>")
    else:
        c2.append(f"<p>Bij {esc(de(homeN))} en {esc(de(awayN))} zijn op dit moment geen blessures of schorsingen gemeld.</p>")
    c2.append("<h3>Recente vorm</h3>")
    c2.append(f"<p>Resultaten van de laatste wedstrijden in alle competities (W = winst, G = gelijk, V = verlies; recentste rechts):</p>")
    c2.append(_form_regel(homeN, hForm))
    c2.append(_form_regel(awayN, aForm))
    content2 = "\n".join(c2)

    # ---- CONTENT-3 (deel 3/3): H2H + winkansen + FAQ ----
    c3 = []
    c3.append("<h3>Onderlinge duels</h3>")
    # alleen duels met een geldige einduitslag (filter afgelaste/lege wedstrijden)
    h2h_ok = [m for m in (h2h or [])
              if (m.get("goals") or {}).get("home") is not None
              and (m.get("goals") or {}).get("away") is not None]
    if h2h_ok:
        c3.append("<p>De recente onderlinge geschiedenis tussen beide ploegen:</p>")
        c3.append("<ul>" + "".join("<li>"+esc(_h2h_line(m))+"</li>" for m in h2h_ok[:5]) + "</ul>")
    else:
        c3.append("<p>Beide ploegen speelden de afgelopen jaren niet of nauwelijks tegen elkaar, "
                  "waardoor er geen recente onderlinge statistieken beschikbaar zijn.</p>")
    c3.append("<h3>Winkansen volgens de statistische voorspelling</h3>")
    if has_pred:
        c3.append("<p>Let op: dit is <strong>geen wedtip van Bet-Experts</strong>, maar een statistische voorspelling "
                  "op basis van vorm, onderlinge duels en teamsterkte:</p>")
        c3.append(f"<ul><li>{esc(homeN)} wint: <strong>{pH}%</strong></li>"
                  f"<li>Gelijkspel: <strong>{pD}%</strong></li>"
                  f"<li>{esc(awayN)} wint: <strong>{pA}%</strong></li></ul>")
        c3.append(f"<p>{_model_zin(homeN, awayN, pH, pD, pA)}</p>")
    else:
        c3.append("<p>Voor dit duel is er geen betrouwbare statistische voorspelling beschikbaar."
                  + ("" if definitief else " Zodra de winkansen bekend zijn, werken we ze hier bij.") + "</p>")
    c3.append("<h3>Veelgestelde vragen</h3>")
    c3.append(_faq(homeN, awayN, hLU, aLU, definitief, kickoff, flip_dt, dt, pH, pD, pA, has_pred, tv_faq))
    c3.append(f'<p><a href="{HUB_PATH}"><strong>Bekijk alle vermoedelijke en definitieve opstellingen</strong></a></p>')
    content3 = "\n".join(c3)

    return content, content2, content3

EXTERN = ("footymetrics", "extern")   # externe voorspelling (FootyMetrics of de uurlijks bijgewerkte bron)

def _zelfde_naam(a, b):
    """Dezelfde speler bij een andere schrijfwijze? 'P. Cubarsí' ~ 'Pau Cubarsí Paredes',
    'A. Markhiev' ~ 'A. Marhiev', 'T. Mütallimov' ~ 'T. Mütəllimov'."""
    import difflib
    ta = [t for t in _fold(a).replace(".", " ").split() if t]
    tb = [t for t in _fold(b).replace(".", " ").split() if t]
    if not ta or not tb:
        return False
    la, lb = ta[-1], tb[-1]
    # voorletter moet kloppen ('J. Timber' is niet 'Q. Timber'), tenzij een van beide maar één naam heeft ('Vitinha')
    if len(ta) > 1 and len(tb) > 1 and ta[0][:1] != tb[0][:1]:
        return False
    if la == lb:
        return True
    if (len(la) >= 4 and la in tb) or (len(lb) >= 4 and lb in ta):
        return True                              # 'P. Cubarsí' / 'Pau Cubarsí Paredes'
    return min(len(la), len(lb)) >= 4 and difflib.SequenceMatcher(None, la, lb).ratio() >= 0.8

def _verschil(pred_names, prev_names):
    """-> (erin, eruit): namen uit de voorspelling zonder tegenhanger in de vorige elf en andersom."""
    eruit = list(prev_names)
    erin = []
    for n in pred_names:
        hit = next((m for m in eruit if _zelfde_naam(n, m)), None)
        if hit is None:
            erin.append(n)
        else:
            eruit.remove(hit)
    return erin, eruit

def _xi_lijst(lu):
    return [(pp.get("player") or {}).get("name") for pp in _players(lu) if (pp.get("player") or {}).get("name")]

def footy_note(pred, last, team, absent=None):
    """Voorspelde elf (FootyMetrics) vs. een recent gespeelde elf -> wijzigingen-zin.
    'last' mag één opstelling zijn of een lijst (recentste eerst): dan telt de opstelling die het meest op de
    voorspelling lijkt (een B-elftal in een oefenduel zegt weinig), met de juiste verwijzing in de zin."""
    prevs = [p for p in (last if isinstance(last, list) else [last]) if p and _players(p)]
    if not pred or not prevs: return ""
    pn = _xi_lijst(pred)
    diffs = [_verschil(pn, _xi_lijst(p)) for p in prevs]
    idx = min(range(len(prevs)), key=lambda i: (len(diffs[i][0]), i))
    ref = "de vorige wedstrijd" if idx == 0 else "de basiself van twee wedstrijden geleden"
    erin, eruit = diffs[idx]
    ab = [x for x in (absent or set()) if x]
    if not erin:
        return (f"{De(team)} {ww(team, 'begint', 'beginnen')} naar verwachting met dezelfde elf als in de vorige wedstrijd."
                if idx == 0 else
                f"{De(team)} {ww(team, 'begint', 'beginnen')} naar verwachting met dezelfde elf als twee wedstrijden geleden.")
    if len(erin) <= 3:
        uit = [f"{esc(n)}{' (afwezig)' if any(_zelfde_naam(n, x) for x in ab) else ''}" for n in eruit]
        return (f"Ten opzichte van {ref} verwachten we {TELWOORD.get(len(erin))} "
                f"{'wijziging' if len(erin) == 1 else 'wijzigingen'} bij {de(team)}: "
                f"<strong>{esc(', '.join(erin))}</strong> erin"
                + (f", {', '.join(uit)} eruit." if uit else "."))
    return (f"{De(team)} {ww(team, 'wijzigt', 'wijzigen')} naar verwachting flink: {len(erin)} nieuwe namen ten opzichte van {ref}, "
            f"onder wie <strong>{esc(', '.join(erin[:3]))}</strong>.")

def _lineup_block(team, lu, prev, definitief, kickoff, flip, is_home, absent=None):
    h = [f"<h3>{'Bevestigde' if definitief else 'Vermoedelijke'} opstelling {esc(team)}"
         + (f" ({esc(formation(lu))})" if lu and formation(lu) else "") + "</h3>"]
    if lu and _players(lu):
        h.append(f"<p><strong>{'Bevestigde' if definitief else 'Vermoedelijke'} elf:</strong> {xi_line(lu)}.</p>")
        if not definitief:
            footy = lu.get("source") in EXTERN
            note = footy_note(lu, prev, team, absent) if footy else rotation_note(lu, prev, team, absent)
            if note:
                h.append(f"<p>{note}</p>")
            h.append(f"<strong>De definitieve opstelling van {esc(de(team))} volgt ongeveer één uur voor de aftrap "
                     f"(rond {flip} uur)</strong> en wordt hier automatisch bijgewerkt zodra die officieel bekend is.")
            h[-1] = "<p>"+h[-1]+"</p>"
    else:
        h.append(f"<p>De opstelling van <strong>{esc(de(team))}</strong> is nog niet bekend. Deze wordt hier bijgewerkt "
                 f"zodra er teamnieuws binnenkomt, en definitief rond {flip} uur.</p>")
    # geen bronvermelding "op basis van de voorspelling van FootyMetrics" meer (gebruiker, 01-10-2026)
    return "\n".join(h)

# ---------- vorm ----------
def form_dashes(f):
    m = {"W":"W","D":"G","L":"V"}
    return "–".join(m.get(c, c) for c in (f or "")[-5:])

def _aantal(n, ev, mv):
    return f"{TELWOORD.get(n, n)} {ev if n == 1 else mv}"

def _opsomming(delen):
    delen = [d for d in delen if d]
    return delen[0] if len(delen) == 1 else ", ".join(delen[:-1]) + " en " + delen[-1]

def form_zin(f, home=None):
    """Beschrijving die klopt met de reeks (chronologisch, recentste rechts)."""
    f = (f or "")[-5:]
    n = len(f); w, d, l = f.count("W"), f.count("D"), f.count("L")
    if n == 0:
        return ""
    if n == 1:
        return {"W": "Won de enige recente wedstrijd.", "D": "Speelde de enige recente wedstrijd gelijk.",
                "L": "Verloor de enige recente wedstrijd."}.get(f, "")
    telling = _opsomming([_aantal(w, "zege", "zeges") if w else "",
                          _aantal(d, "gelijkspel", "gelijke spelen") if d else "",
                          _aantal(l, "nederlaag", "nederlagen") if l else ""])
    if n == 2:
        if w == 2: return "Won beide duels."
        if l == 2: return "Verloor beide duels."
        if d == 2: return "Speelde beide duels gelijk."
        return f"Uit de laatste twee duels: {telling}."
    N = TELWOORD.get(n, n)
    if w == n:
        return f"Won alle laatste {N} wedstrijden: de vorm is uitstekend."
    if l == n:
        return f"Verloor alle laatste {N} wedstrijden: de vorm is ver te zoeken."
    if l == 0:
        return f"Ongeslagen in de laatste {N} wedstrijden ({telling})" + (": de vorm zit goed." if w >= 3 else ".")
    if w == 0:
        return f"Zonder zege in de laatste {N} wedstrijden ({telling})."
    reeks = len(f) - len(f.rstrip(f[-1]))          # hoeveel keer op rij hetzelfde resultaat aan het eind
    if w >= 3:
        return (f"{cap(telling)} in de laatste {N}: de vorm zit goed"
                + (", al ging het laatste duel verloren." if f[-1] == "L" else "."))
    if l >= 3:
        if f[-1] == "W":
            return (f"{cap(telling)} in de laatste {N}, maar " +
                    ("het laatste duel werd gewonnen." if reeks == 1 else f"de laatste {TELWOORD.get(reeks, reeks)} duels werden gewonnen."))
        return f"{cap(telling)} in de laatste {N}: de resultaten vallen tegen."
    return f"Wisselvallige reeks: {telling} in de laatste {N} wedstrijden."

def _form_regel(team, f):
    if not f:
        return f"<p><strong>{esc(team)}:</strong> geen recente uitslagen bekend.</p>"
    return f"<p><strong>{esc(team)}:</strong> {form_dashes(f)}. {form_zin(f)}</p>"

def _h2h_line(m):
    fx=m.get("fixture",{}); dt=(fx.get("date","") or "")[:10]
    t=m.get("teams",{}); g=m.get("goals",{})
    try:
        y,mo,d = dt.split("-"); dts=f"{int(d)} {MAAND[int(mo)-1]} {y}"
    except Exception:
        dts=dt
    return (f"{dts}: {nl_name(t.get('home',{}).get('name'))} {g.get('home')}-{g.get('away')} "
            f"{nl_name(t.get('away',{}).get('name'))}")

FAV_DREMPEL = 12   # procentpunt verschil met de nummer twee voordat we van 'favoriet' spreken

def _model_zin(homeN, awayN, pH,pD,pA):
    if abs(pH-pA) <= FAV_DREMPEL:
        return ("De statistische voorspelling ziet een gelijkopgaand duel: de winkansen van beide ploegen "
                "liggen dicht bij elkaar.")
    fav = homeN if pH>=pA else awayN
    if max(pH, pA) >= 60:
        return f"De statistische voorspelling wijst {esc(de(fav))} aan als duidelijke favoriet."
    return f"De statistische voorspelling wijst {esc(de(fav))} aan als favoriet, maar rekent op een pittige wedstrijd."

def tv_info(card, homeN, awayN):
    """Uit een waaroptv-kaart: (infoblok-regel (label, waarde), FAQ (vraag, antwoord)) of (None, None)."""
    if not card:
        return None, None
    tv = card.get("tv") or []; bm = card.get("bookmakers") or []
    vraag = f"Op welke zender is {homeN} – {awayN} te zien?"
    if tv:
        zender = " en ".join(tv)
        npo = all(z.upper().startswith("NPO") for z in tv)
        extra = (" (gratis)" if npo else " (basispakket)") if card.get("gratis") else ""
        antw = f"{homeN} – {awayN} is in Nederland live te zien op {zender}"
        antw += (". De wedstrijd is gratis te zien, ook online via NPO Start." if npo and card.get("gratis") else
                 ", dat in het basispakket van de meeste tv-aanbieders zit." if card.get("gratis") else ".")
        return ("Live op tv", zender + extra), (vraag, antw)
    if bm:
        stream = " en ".join(bm)
        return (("Livestream", stream),
                (vraag, f"{homeN} – {awayN} is niet op de Nederlandse tv te zien, maar wel live te streamen bij {stream}."))
    return None, None

def _flip_moment(flip_dt):
    """'rond 19:45 uur op zaterdag 3 oktober 2026' / 'rond 01:00 uur in de nacht van zaterdag 3 op zondag 4 oktober 2026'."""
    if is_nacht(flip_dt):
        return f"rond {nl_tijd(flip_dt)} uur in de {nacht_label(flip_dt)}"
    return f"rond {nl_tijd(flip_dt)} uur op {nl_datum(flip_dt)}"

def _faq(homeN, awayN, hLU, aLU, definitief, kickoff, flip_dt, dt, pH,pD,pA, has_pred=True, tv_faq=None):
    fav = homeN if pH>=pA else awayN; favp = max(pH,pA)
    # formatie alleen noemen als de bron die kent (geen gok)
    hf = formation(hLU) if hLU else ""; af = formation(aLU) if aLU else ""
    q = []
    if definitief:
        a1 = (f"{De(homeN)} {ww(homeN, 'speelt', 'spelen')} in een {hf}. " if hf else
              f"De definitieve elf van {de(homeN)} staat hierboven. ") + "De opstelling is officieel bevestigd."
    else:
        a1 = (f"{De(homeN)} {ww(homeN, 'speelt', 'spelen')} vermoedelijk in een {hf}. " if hf else
              f"De vermoedelijke elf van {de(homeN)} staat hierboven. ") + \
             f"De definitieve opstelling wordt ongeveer een uur voor de aftrap van {kickoff} uur bevestigd en hier direct bijgewerkt."
    q.append((f"Wat is de {'definitieve' if definitief else 'vermoedelijke'} opstelling van {de(homeN)} tegen {de(awayN)}?", a1))
    if not definitief:
        q.append((f"Wanneer is de definitieve opstelling van {homeN} – {awayN} bekend?",
                  f"Doorgaans ongeveer 60 minuten voor de aftrap, dus {_flip_moment(flip_dt)}."))
    if definitief:
        a3 = (f"{De(awayN)} {ww(awayN, 'begint', 'beginnen')} in een {af}." if af else
              f"De opstelling van {de(awayN)} staat hierboven; de formatie is niet officieel vermeld.")
    elif af:
        a3 = (f"{De(awayN)} {ww(awayN, 'begint', 'beginnen')} naar verwachting in een {af}."
              if (aLU or {}).get("source") in EXTERN else
              f"{De(awayN)} {ww(awayN, 'speelde', 'speelden')} de laatste wedstrijd in een {af} en "
              f"{ww(awayN, 'treedt', 'treden')} naar verwachting ook nu in die formatie aan.")
    else:
        a3 = (f"De formatie van {de(awayN)} is vooraf nog niet bekend; die wordt duidelijk zodra de opstelling "
              f"ongeveer een uur voor de aftrap bevestigd is.")
    q.append((f"In welke formatie {ww(awayN, 'speelt', 'spelen')} {de(awayN)}?", a3))
    if has_pred and abs(pH - pA) > FAV_DREMPEL:
        q.append((f"Wie is de favoriet bij {homeN} – {awayN}?",
                  f"Volgens de statistische voorspelling {ww(fav, 'is', 'zijn')} {de(fav)} favoriet met {favp}% winkans. "
                  f"{homeN}: {pH}%, gelijkspel: {pD}%, {awayN}: {pA}%."))
    if tv_faq:
        q.append(tv_faq)
    out = []
    for question, ans in q:
        out.append(f"<p><strong>{esc(question)}</strong><br>{esc(ans)}</p>")
    return "\n".join(out)
