# -*- coding: utf-8 -*-
"""Bouwt titel, samenvatting en de 3 rich-text content-delen voor een
opstellingen-artikel. Alleen Webflow-compatibele HTML: <p> <h3> <ul> <li>
<strong> <br> <a>. GEEN tabellen."""
import random, html
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    TZ = None
from oa_config import club_slug, reason_nl, HUB_PATH

DAGEN = ["maandag","dinsdag","woensdag","donderdag","vrijdag","zaterdag","zondag"]
MAAND = ["januari","februari","maart","april","mei","juni","juli","augustus",
         "september","oktober","november","december"]

def _local(dt_iso):
    dt = datetime.fromisoformat(dt_iso.replace("Z","+00:00"))
    if TZ: dt = dt.astimezone(TZ)
    return dt

def nl_datum(dt): return f"{DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]} {dt.year}"
def nl_tijd(dt):  return f"{dt.hour:02d}:{dt.minute:02d}"
def esc(s): return html.escape(str(s or ""), quote=False)

# ---------- opstelling-regel ----------
def _players(lu):
    return lu.get("startXI") or []

def xi_line(lu):
    """'K. Haug; A. Sampsted, J. Dirksen ...; spits' — regels gescheiden per linie."""
    rows = {}
    for pp in _players(lu):
        p = pp.get("player") or {}
        grid = (p.get("grid") or "0:0")
        row = grid.split(":")[0]
        rows.setdefault(row, []).append((int(grid.split(":")[1]) if ":" in grid else 0, p.get("name") or ""))
    if not rows:  # geen grid -> gewoon op volgorde
        names = [ (pp.get("player") or {}).get("name","") for pp in _players(lu) ]
        return ", ".join(esc(n) for n in names if n)
    parts = []
    for r in sorted(rows, key=lambda x:int(x)):
        line = [esc(n) for _,n in sorted(rows[r])]
        parts.append(", ".join(line))
    return "; ".join(parts)

def formation(lu): return lu.get("formation") or ""

def _xi_names(lu):
    return set((pp.get("player") or {}).get("name","") for pp in _players(lu))

def rotation_note(last, prev, team):
    """Detecteert wisselingen tussen de laatste twee opstellingen -> positiestrijd-zin."""
    if not last or not prev: return ""
    a, b = _xi_names(last), _xi_names(prev)
    nieuw = [n for n in a - b if n]
    eruit = [n for n in b - a if n]
    if not nieuw:
        return (f"{team} koos in de laatste twee wedstrijden vrijwel dezelfde basiself — "
                f"veel verrassingen zijn niet te verwachten.")
    if len(nieuw) == 1 and len(eruit) == 1:
        return (f"De grootste vraag bij {team} is de strijd om één basisplaats: waar in het laatste duel "
                f"<strong>{esc(nieuw[0])}</strong> startte, kreeg een wedstrijd eerder <strong>{esc(eruit[0])}</strong> de voorkeur. "
                f"Die positiestrijd is dé keuze waar de trainer vlak voor aftrap knopen over doorhakt.")
    return (f"{team} roteerde de laatste wedstrijden op enkele posities "
            f"(o.a. {esc(', '.join(nieuw[:3]))}) — de definitieve keuzes worden vlak voor aftrap duidelijk.")

# ---------- blessures ----------
def injuries_sentence(team, inj_list):
    seen, out = set(), []
    for i in (inj_list or [])[-20:]:
        pl = i.get("player") or {}
        nm = pl.get("name"); rs = pl.get("reason")
        if nm and nm not in seen:
            seen.add(nm); out.append(f"{esc(nm)} ({esc(reason_nl(rs))})")
    if not out:
        return f"<strong>{esc(team)}:</strong> geen bekende afwezigen — de trainer kan uit een fitte selectie kiezen."
    return f"<strong>{esc(team)}:</strong> " + ", ".join(out[:8]) + " ontbreken."

# ---------- titel + samenvatting ----------
def _hook(homeN, awayN, city, pH, pA, has_pred=True):
    # Nederlands, gevarieerd, zonder (Engelse) stadsnamen
    if not has_pred:
        return random.choice([
            "wie start er in de basis?",
            "dit zijn de verwachte namen",
            "de vermoedelijke elftallen op een rij",
            "wie krijgt de voorkeur?",
            "zo verschijnen beide ploegen aan de aftrap",
            "het verwachte teamnieuws",
            "de basiself onder de loep",
            "wie begint er vandaag?",
        ])
    fav, und, favp = (homeN, awayN, pH) if pH>=pA else (awayN, homeN, pA)
    if abs(pH-pA) <= 12:
        return random.choice([
            "een gelijkopgaand duel",
            f"{homeN} en {awayN} aan elkaar gewaagd",
            "alles kan in dit duel",
            "een spannende clash op komst",
            "wie trekt aan het langste eind?",
            "de krachten in evenwicht",
            "kan iedereen hier winnen",
        ])
    if favp >= 65:
        return random.choice([
            f"{fav} torenhoog favoriet",
            f"{fav} de gedoodverfde favoriet",
            f"{fav} moet het karwei klaren",
            f"{fav} jaagt op de volle buit",
            f"kan {und} verrassen?",
            f"{fav} is de grote favoriet",
        ])
    return random.choice([
        f"{fav} licht favoriet",
        f"{fav} favoriet, maar {und} loert",
        f"{fav} aan zet",
        f"{fav} met de beste papieren",
        f"{fav} start als favoriet",
        f"loert {und} op een stunt?",
    ])

def build_title(definitief, homeN, awayN, city, pH, pA, has_pred=True):
    kind = "Definitieve opstelling" if definitief else "Vermoedelijke opstelling"
    hook = _hook(homeN, awayN, city, pH, pA, has_pred)
    hook = hook[0].upper()+hook[1:]
    return f"{kind} {homeN} – {awayN} | {hook}"

def build_samenvatting(definitief, homeN, awayN, comp, dt):
    kind = "Definitieve" if definitief else "Vermoedelijke"
    s = (f"{kind} opstellingen {homeN} – {awayN} ({comp}, {DAGEN[dt.weekday()]} {dt.day} {MAAND[dt.month-1]}): "
         f"bekijk de {'bevestigde' if definitief else 'verwachte'} basiselftallen, blessures, vorm en de winkansen volgens het AI-model.")
    return s[:250]

def slugify(s):
    import re
    return re.sub(r"-+","-", re.sub(r"[^a-z0-9]+","-", (s or "").lower())).strip("-")

def build_slug(home_slug, away_slug, dt):
    return f"opstelling-{home_slug}-{away_slug}-{dt.day:02d}-{dt.month:02d}-{dt.year}"

# ---------- content-delen ----------
def build_content(ctx):
    """ctx bevat alle opgehaalde data. Retourneert (content, content2, content3)."""
    homeN, awayN = ctx["homeN"], ctx["awayN"]
    hSlug, aSlug = ctx["hSlug"], ctx["aSlug"]
    compSlug, compN = ctx["compSlug"], ctx["compN"]
    dt = ctx["dt"]; city = ctx["city"]; venue = ctx["venue"]; ronde = ctx["ronde"]
    definitief = ctx["definitief"]
    pH,pD,pA = ctx["pH"],ctx["pD"],ctx["pA"]
    has_pred = ctx.get("has_pred", True)
    hForm,aForm = ctx["hForm"], ctx["aForm"]
    hLU,aLU = ctx["hLU"], ctx["aLU"]              # laatste opstelling (predicted) of bevestigd
    hPrev,aPrev = ctx["hPrev"], ctx["aPrev"]      # vorige opstelling (voor rotatie)
    hInj,aInj = ctx["hInj"], ctx["aInj"]
    h2h = ctx["h2h"]
    kickoff = nl_tijd(dt)
    from datetime import timedelta
    flip = nl_tijd(dt - timedelta(hours=1))
    datum = nl_datum(dt)

    def clublink(slug, name):
        return f'<a href="/clubs/{slug}">{esc(name)}</a>' if slug else f"<strong>{esc(name)}</strong>"
    hLink = clublink(hSlug, homeN); aLink = clublink(aSlug, awayN)
    compLink = f'<a href="/competities/{compSlug}">{esc(compN)}</a>' if compSlug else f"<strong>{esc(compN)}</strong>"

    lbl = "De bevestigde" if definitief else "De vermoedelijke"
    kop = "bevestigde" if definitief else "vermoedelijke"

    # ---- CONTENT (deel 1/3): intro + info + thuisploeg-opstelling ----
    c1 = []
    fav = homeN if pH>=pA else awayN
    c1.append(f'<p><a href="{HUB_PATH}">‹ Alle opstellingen</a></p>')
    c1.append(f"<p><strong>Op {datum} om {kickoff} uur ontvangt {hLink} in {esc(venue or city)} {aLink} "
              f"in speelronde {ronde} van de {compLink}. Hieronder vind je de {kop} opstellingen van beide ploegen, "
              f"de blessures en schorsingen, de recente vorm, de onderlinge duels en de winkansen volgens ons AI-model.</strong></p>")
    c1.append("<h3>📅 Wedstrijdinformatie</h3>")
    c1.append(f"<p><strong>Wedstrijd:</strong> {esc(homeN)} – {esc(awayN)}<br>"
              f"<strong>Competitie:</strong> {esc(compN)} – Speelronde {ronde}<br>"
              f"<strong>Datum:</strong> {datum}<br>"
              f"<strong>Aanvangstijd:</strong> {kickoff} uur<br>"
              f"<strong>Stadion:</strong> {esc(venue or city)}</p>")
    # thuisploeg opstelling
    c1.append(_lineup_block(homeN, hLU, hPrev, definitief, kickoff, flip, is_home=True))
    content = "\n".join(c1)

    # ---- CONTENT-2 (deel 2/3): uitploeg-opstelling + blessures + vorm ----
    c2 = []
    c2.append(_lineup_block(awayN, aLU, aPrev, definitief, kickoff, flip, is_home=False))
    c2.append("<h3>🩺 Blessures &amp; schorsingen</h3>")
    c2.append("<p>De trainers moeten rekening houden met de volgende afwezigen:</p>")
    c2.append("<ul><li>"+injuries_sentence(homeN, hInj)+"</li><li>"+injuries_sentence(awayN, aInj)+"</li></ul>")
    c2.append("<h3>📈 Recente vorm</h3>")
    c2.append(f"<p><strong>{esc(homeN)}:</strong> {form_dashes(hForm)}. {form_zin(hForm, True)}</p>")
    c2.append(f"<p><strong>{esc(awayN)}:</strong> {form_dashes(aForm)}. {form_zin(aForm, False)}</p>")
    content2 = "\n".join(c2)

    # ---- CONTENT-3 (deel 3/3): H2H + AI-kansen + FAQ ----
    c3 = []
    c3.append("<h3>🤝 Onderlinge duels</h3>")
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
    c3.append("<h3>🔮 Winkansen volgens het AI-model</h3>")
    if has_pred:
        c3.append("<p>Let op: dit is <strong>geen wedtip van Bet-Experts</strong>, maar de kansberekening van een "
                  "statistisch AI-model op basis van vorm, onderlinge duels en teamsterkte:</p>")
        c3.append(f"<ul><li>{esc(homeN)} wint: <strong>{pH}%</strong></li>"
                  f"<li>Gelijkspel: <strong>{pD}%</strong></li>"
                  f"<li>{esc(awayN)} wint: <strong>{pA}%</strong></li></ul>")
        c3.append(f"<p>{_model_zin(homeN, awayN, pH, pD, pA)}</p>")
    else:
        c3.append("<p>Voor dit duel is er nog geen betrouwbare modelvoorspelling beschikbaar. "
                  "Zodra de winkansen bekend zijn, werken we ze hier bij.</p>")
    c3.append("<h3>❓ Veelgestelde vragen</h3>")
    c3.append(_faq(homeN, awayN, hLU, aLU, definitief, kickoff, flip, datum, pH, pD, pA, has_pred))
    c3.append(f'<p>👉 <a href="{HUB_PATH}"><strong>Bekijk alle vermoedelijke en definitieve opstellingen van vandaag</strong></a></p>')
    content3 = "\n".join(c3)

    return content, content2, content3

def _lineup_block(team, lu, prev, definitief, kickoff, flip, is_home):
    emoji = "🏟️" if is_home else "🚌"
    h = [f"<h3>{emoji} {'Bevestigde' if definitief else 'Vermoedelijke'} opstelling {esc(team)}"
         + (f" ({esc(formation(lu))})" if lu and formation(lu) else "") + "</h3>"]
    if lu and _players(lu):
        h.append(f"<p><strong>{'Bevestigde' if definitief else 'Vermoedelijke'} elf:</strong> {xi_line(lu)}.</p>")
        if not definitief:
            h.append(f"<p>{rotation_note(lu, prev, team)}</p>")
            h.append(f"👉 <strong>De definitieve opstelling van {esc(team)} volgt ongeveer één uur voor de aftrap "
                     f"(rond {flip} uur)</strong> en wordt hier automatisch bijgewerkt zodra de club die bevestigt.")
            h[-1] = "<p>"+h[-1]+"</p>"
    else:
        h.append(f"<p>De opstelling van <strong>{esc(team)}</strong> is nog niet bekend. Deze wordt hier bijgewerkt "
                 f"zodra er teamnieuws binnenkomt, en definitief rond {flip} uur.</p>")
    return "\n".join(h)

def form_dashes(f):
    m = {"W":"W","D":"G","L":"V"}
    return "–".join(m.get(c, c) for c in (f or "")[:5]) or "n.n.b."

def form_zin(f, home):
    w = (f or "").count("W"); l=(f or "").count("L")
    if w>=3: return "De laatste weken zit de vorm goed."
    if l>=3: return "De resultaten vielen de laatste weken tegen."
    return "De vorm is wisselvallig met wins en verliezen door elkaar."

def _h2h_line(m):
    fx=m.get("fixture",{}); dt=(fx.get("date","") or "")[:10]
    t=m.get("teams",{}); g=m.get("goals",{})
    try:
        y,mo,d = dt.split("-"); dts=f"{int(d)} {MAAND[int(mo)-1]} {y}"
    except Exception:
        dts=dt
    return f"{dts}: {t.get('home',{}).get('name')} {g.get('home')}-{g.get('away')} {t.get('away',{}).get('name')}"

def _model_zin(homeN, awayN, pH,pD,pA):
    if abs(pH-pA)<=12:
        return (f"Het model ziet een competitief, gelijkopgaand duel — de kansen op winst en een gelijkspel "
                f"liggen dicht bij elkaar.")
    fav = homeN if pH>=pA else awayN
    return f"Het model wijst {esc(fav)} aan als favoriet, maar rekent op een pittige wedstrijd."

def _faq(homeN, awayN, hLU, aLU, definitief, kickoff, flip, datum, pH,pD,pA, has_pred=True):
    fav = homeN if pH>=pA else awayN; favp = max(pH,pA)
    hf = formation(hLU) if hLU else "4-3-3"; af = formation(aLU) if aLU else "4-3-3"
    q = []
    q.append((f"Wat is de {'definitieve' if definitief else 'vermoedelijke'} opstelling van {homeN} tegen {awayN}?",
              f"{homeN} speelt {'in' if definitief else 'vermoedelijk in'} een {hf}. "
              + ("De opstelling is bevestigd en hierboven te zien." if definitief else
                 f"De definitieve opstelling wordt ongeveer een uur voor de aftrap van {kickoff} uur bevestigd en hier direct bijgewerkt.")))
    q.append((f"Wanneer is de definitieve opstelling van {homeN} – {awayN} bekend?",
              f"Doorgaans ongeveer 60 minuten voor de aftrap, dus rond {flip} uur op {datum}."))
    q.append((f"In welke formatie speelt {awayN}?",
              f"{awayN} speelde de laatste wedstrijden in een {af} en treedt naar verwachting ook nu in die formatie aan."))
    if has_pred:
        q.append((f"Wie is de favoriet bij {homeN} – {awayN}?",
                  f"Volgens het AI-model is {fav} favoriet met {favp}% winkans. {homeN}: {pH}%, gelijkspel: {pD}%, {awayN}: {pA}%."))
    out = []
    for question, ans in q:
        out.append(f"<p><strong>{esc(question)}</strong><br>{esc(ans)}</p>")
    return "\n".join(out)
