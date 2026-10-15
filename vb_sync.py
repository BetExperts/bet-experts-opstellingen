# -*- coding: utf-8 -*-
"""Voorbeschouwingen: opstellingen gelijktrekken met het laatste nieuws (gebruiker, 15-10-2026).

Voor elke voorbeschouwing (nieuwste 300 CMS-items, veld fixture-id) met aftrap in de komende 48 uur:
  1. vermoedelijke elf van opstellingvandaag.nl (anders FootyMetrics), zoals de opstellingen-artikelen;
     zodra API-Football de officiële opstellingen heeft: die;
  2. namen koppelen aan de spelers van de eigen API (oa_xi: volledige naam, rugnummer, positie);
  3. de twee regels 'Vermoedelijke opstelling <ploeg> (formatie): …' in content-2 herschrijven
     (de rest van de tekst, ook de afwezigen, blijft staan);
  4. dezelfde elf in Cloudflare KV zetten (fx:<fixture-id>), zodat het opstellingen-blok op de pagina
     (/api/voorspeld/<id>, worker 'voorspeld-api') exact dezelfde elf tekent.
Nooit de bron noemen in de tekst. Geen externe voorspelling gevonden -> niets wijzigen (de tekst houdt
'Gebaseerd op laatste duel', het blok valt terug op de laatst gespeelde elf).

Draait mee met run_finalize_mac.sh (elke 5 min); per wedstrijd hooguit elk uur, binnen 3 uur voor de
aftrap elke 10 minuten. Tijdsbudget per run, zodat finalize niet op deze stap wacht.
  python3 vb_sync.py [--dry] [--fixture <id>] [--force]
"""
import argparse, hashlib, html, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import oa_api as api
import oa_footy as FOOTY
import oa_ovandaag as OV
import oa_xi as X
import oa_webflow as WF
from oa_config import BASE, NIEUWS_COLLECTION, WF_API, nl_name
from oa_match import _team_lineup

NL = ZoneInfo("Europe/Amsterdam")
STATE = os.path.join(BASE, "state", "voorbeschouwingen.json")
KV_NS = open(os.path.join(BASE, "cloudflare", "kv_namespace.txt")).read().strip()
VENSTER_U = 48
BUDGET_S = int(os.environ.get("VB_BUDGET_S", "240"))
KV_TTL = 4 * 24 * 3600
MAANDEN = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}

# Regel in de voorbeschouwing (preview-agent): <p><strong><a …>Vermoedelijke opstelling</a> Ploeg (4-3-3):</strong> …</p>
P_RE = re.compile(r'<p><strong>(?P<a><a\b[^>]*>)?(?P<lbl>Vermoedelijke|Definitieve|Verwachte) opstelling(?P<ae></a>)?'
                  r'\s+(?P<team>[^<]+?)(?:\s+\((?P<f>[^)]*)\))?:</strong>.*?</p>', re.S)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def voorbeschouwingen(aantal=300):
    """{fixture-id: (item, aftrap)} van de nieuwste live voorbeschouwingen, rechtstreeks uit de CMS
    (geen paginaverkeer). Voorbeschouwingen worden 1-3 dagen vooraf gemaakt, dus de nieuwste 300 items volstaan."""
    out = {}
    for off in range(0, aantal, 100):
        r = WF._req("GET", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items/live"
                           f"?limit=100&offset={off}&sortBy=createdOn&sortOrder=desc")
        for it in (r or {}).get("items") or []:
            fd = it["fieldData"]
            fid, d = str(fd.get("fixture-id") or ""), fd.get("datum-tijd-van-wedstrijd")
            if "wedtips" not in fd.get("slug", "") or not fid.isdigit() or not d:
                continue
            ko = datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(NL)
            out.setdefault(fid, (it, ko))
    return out


def kv_put(fid, obj):
    acc, tok = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    url = (f"https://api.cloudflare.com/client/v4/accounts/{acc}/storage/kv/namespaces/{KV_NS}/values/fx:{fid}"
           f"?expiration_ttl={KV_TTL}")
    req = urllib.request.Request(url, data=json.dumps(obj, ensure_ascii=False).encode(), method="PUT",
                                 headers={"Authorization": "Bearer " + tok, "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30)).get("success")


def _full(lu):
    return bool(lu and len(lu.get("startXI") or []) >= 11)


def opstellingen(fx):
    """(status, {teamId: lineup}) — status 'definitief' | 'voorspeld' | None."""
    fid = fx["fixture"]["id"]; th, ta = fx["teams"]["home"], fx["teams"]["away"]
    lus = {str((lu.get("team") or {}).get("id")): lu for lu in api.lineups(fid)}
    if _full(lus.get(str(th["id"]))) and _full(lus.get(str(ta["id"]))):
        return "definitief", {str(th["id"]): lus[str(th["id"])], str(ta["id"]): lus[str(ta["id"])]}
    ymd = datetime.fromisoformat(fx["fixture"]["date"].replace("Z", "+00:00")).astimezone(NL).date().isoformat()
    hN, aN = nl_name(th["name"]), nl_name(ta["name"])
    fm, ordered = OV.predicted([hN, th["name"]], [aN, ta["name"]], ymd), True
    if not fm:
        fm, ordered = FOOTY.predicted(th["name"], ta["name"], ymd), False
    if not fm:
        return None, {}
    out = {}
    for t, side in ((th, fm["home"]), (ta, fm["away"])):
        vorige = _team_lineup(t["id"], exclude_fixture=fid, want=3)
        xi, form = X.build(side["names"], side.get("formation"), X.pool_from(vorige), ordered)
        if not xi:
            return None, {}
        coach = next((lu.get("coach") for lu in vorige if lu.get("coach")), None)
        out[str(t["id"])] = {"team": {"id": t["id"], "name": t["name"], "logo": t.get("logo")},
                             "formation": form, "startXI": xi, "substitutes": [], "coach": coach}
    return "voorspeld", out


def _regel(lu):
    return X.line_text(lu["startXI"] if all(re.fullmatch(r"\d+:\d+", str((p.get("player") or {}).get("grid") or ""))
                                            for p in lu["startXI"]) else
                       [{"player": {**p["player"], "grid": f"1:{i}"}} for i, p in enumerate(lu["startXI"], 1)],
                       esc=html.escape)


def herschrijf(content, status, lus, home_id, away_id, namen):
    """Vervangt de twee opstellingsregels; None als de structuur niet herkend wordt."""
    ms = list(P_RE.finditer(content or ""))
    if len(ms) < 2:
        return None
    fold = lambda s: X.fold(html.unescape(s))
    def welke(team):
        sh = X._score(team, namen[0]) if namen[0] else 0; sa = X._score(team, namen[1]) if namen[1] else 0
        return home_id if sh >= sa else away_id
    eerste = welke(ms[0].group("team").strip())
    toewijzing = [eerste, away_id if eerste == home_id else home_id]
    nieuw, pos = [], 0
    for m, tid in zip(ms[:2], toewijzing):
        lu = lus[str(tid)]
        f = lu.get("formation") or ""
        lbl = "Definitieve" if status == "definitief" else "Vermoedelijke"
        noot = "Officiële opstelling." if status == "definitief" else "Verwachte opstelling op basis van het laatste nieuws."
        p = (f'<p><strong>{m.group("a") or ""}{lbl} opstelling{m.group("ae") or ""} {m.group("team").strip()}'
             f'{f" ({html.escape(f)})" if f else ""}:</strong> {_regel(lu)}. <em>{noot}</em></p>')
        nieuw.append(content[pos:m.start()]); nieuw.append(p); pos = m.end()
    nieuw.append(content[pos:])
    return "".join(nieuw)


def sync_een(fid, item, ko, st, dry=False):
    fx = api.match(fid)
    if not fx:
        return "geen wedstrijddata"
    th, ta = fx["teams"]["home"], fx["teams"]["away"]
    status, lus = opstellingen(fx)
    if not status:
        return "geen externe opstelling (blijft laatste duel)"
    sig = hashlib.sha1(json.dumps([status] + [[lus[str(t["id"])]["formation"]] +
                                              [p["player"]["name"] for p in lus[str(t["id"])]["startXI"]]
                                              for t in (th, ta)], ensure_ascii=False).encode()).hexdigest()[:12]
    if sig == st.get("sig"):
        return f"{status}: ongewijzigd"
    fd = item["fieldData"]
    nieuw = herschrijf(fd.get("content-2") or "", status, lus, th["id"], ta["id"],
                       [nl_name(th["name"]), nl_name(ta["name"])])
    if nieuw is None:
        return "opstellingsregels niet gevonden in de tekst"
    kv = {"fixture": fid, "status": status, "bijgewerkt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "response": [lus[str(th["id"])], lus[str(ta["id"])]]}
    if dry:
        print("     tekst:", re.sub(r"<[^>]+>", "", " | ".join(m.group(0) for m in P_RE.finditer(nieuw)))[:600])
        return f"{status}: zou bijwerken"
    if not kv_put(fid, kv):
        return "KV mislukt"
    if nieuw != fd.get("content-2"):
        WF.update_live(item["id"], {"content-2": nieuw})
    st.update({"sig": sig, "status": status, "item": item["id"], "slug": fd.get("slug")})
    return f"{status}: bijgewerkt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--fixture")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    t0, now = time.time(), datetime.now(NL)
    state = load_state()
    lijst = voorbeschouwingen()
    todo = []
    for fid, (item, ko) in lijst.items():
        if a.fixture and fid != a.fixture:
            continue
        if not a.fixture and not (now - timedelta(minutes=15) <= ko <= now + timedelta(hours=VENSTER_U)):
            continue
        st = state.setdefault(fid, {})
        if st.get("status") == "definitief" and not a.force:
            continue
        interval = 10 if ko - now < timedelta(hours=3) else 55
        last = st.get("gecheckt")
        if last and not a.force and (now - datetime.fromisoformat(last)).total_seconds() < interval * 60:
            continue
        todo.append((ko, last or "", fid, item))
    todo.sort(key=lambda x: (x[1], x[0], x[2]))           # nooit gecheckt eerst, dan vroegste aftrap
    print(f"Voorbeschouwingen: {len(lijst)} recent in de CMS, {len(todo)} te controleren")
    for ko, _, fid, item in todo:
        if time.time() - t0 > BUDGET_S:
            print("  … tijdsbudget op, rest volgende run"); break
        st = state[fid]
        try:
            res = sync_een(fid, item, ko, st, dry=a.dry)
        except Exception as e:
            res = f"fout: {e}"
        print(f"  {ko:%d-%m %H:%M} {item['fieldData']['slug'].removeprefix('wedtips-')[:52]}: {res}")
        if not a.dry:
            st["gecheckt"] = datetime.now(NL).isoformat(timespec="seconds")
    # oude regels opruimen
    grens = (now - timedelta(days=5)).isoformat()
    for fid in [f for f, s in state.items() if s.get("gecheckt", "9") < grens]:
        state.pop(fid)
    if not a.dry:
        save_state(state)


if __name__ == "__main__":
    main()
