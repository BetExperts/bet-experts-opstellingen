# -*- coding: utf-8 -*-
"""Configuratie voor de opstellingen-agent."""
import os, json, re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

# --- Webflow ---
WEBFLOW_TOKEN = os.environ.get("WEBFLOW_TOKEN", "").strip()
NIEUWS_COLLECTION = "64ff0fbd5a8f205b05d54656"
WF_API = "https://api.webflow.com/v2"

# Rubriek (categorie) waaronder het artikel valt — de "Opstellingen"-rubriek.
# Leeg laten ("") als je geen rubriek wilt zetten.
RUBRIEK_ID = "6aa1697a759ee6e460792f36"

# --- Bet-Experts API-proxy (Cloudflare Worker) ---
API = "https://www.bet-experts.nl/api"

# Hub-pagina waar alle opstellingen onder vallen (backlink in elk artikel).
HUB_PATH = "/opstellingen"

# Opschonen: opstellingen-artikelen ouder dan zoveel dagen NA de wedstrijd
# worden door cleanup.py verwijderd (mét redirect-lijst naar de hub).
RETENTION_DAYS = 30

# --- Competities die de agent verwerkt ---
# worker_slug   = slug in de Cloudflare Worker (voor /api/fixtures/{slug})
# comp_slug     = slug van de competitiepagina op de site (voor /competities/<slug>)
# naam          = weergavenaam in de tekst
# comp_id = item-id in de Competities-collectie (voor het referentieveld 'competitie',
# waarop je op de hub kunt filteren/sorteren)
# toppers_only : True = alleen wedstrijden met een 'groot team' (top_teams) krijgen een artikel
LEAGUES = [
    {"worker_slug": "eredivisie",     "comp_slug": "eredivisie",              "naam": "Eredivisie",
     "comp_id": "65de2f987de877fdf6583d10"},
    {"worker_slug": "eerste-divisie", "comp_slug": "keuken-kampioen-divisie", "naam": "Keuken Kampioen Divisie",
     "comp_id": "65de4bc0a8777b9898d6374e"},
    {"worker_slug": "efl-cup",        "comp_slug": "efl-cup",                 "naam": "EFL Cup",
     "comp_id": "66cc403600c5cbae73af3c82", "toppers_only": True,
     "top_teams": ["manchester city", "manchester united", "liverpool", "arsenal", "chelsea",
                   "tottenham", "newcastle", "aston villa", "west ham"]},
    # Nations League: alle wedstrijden (League A t/m D, ~8-10 per speeldag). Landnamen worden
    # via data/landen_nl.json naar het Nederlands vertaald.
    {"worker_slug": "nations-league", "comp_slug": "uefa-nations-league", "naam": "Nations League",
     "comp_id": "66d5a7f7fb9f23ce90376ef4"},
    # Afrika Cup-kwalificatie: alleen Marokko (grote Marokkaanse doelgroep in NL)
    {"worker_slug": "afrika-cup-kwalificatie", "comp_slug": "afrika-cup-of-nations",
     "naam": "Afrika Cup-kwalificatie", "comp_id": "6926ce5a5247b7619744eb7c",
     "toppers_only": True, "top_teams": ["morocco"]},
    # Oefeninterlands: alleen op verzoek (manual_only), via --league friendlies --fixture <id>
    {"worker_slug": "friendlies", "comp_slug": "int-vriendschappelijke-wedstrijden", "naam": "oefeninterland",
     "comp_id": "65f9b20c402bb844e2ad0bf4", "manual_only": True, "vriendschappelijk": True},
]

def is_topper(fx, cfg):
    """True als de wedstrijd een 'topper' is (of als de competitie geen filter kent)."""
    if not cfg.get("toppers_only"):
        return True
    tops = [t.lower() for t in cfg.get("top_teams", [])]
    t = fx.get("teams", {})
    names = ((t.get("home", {}) or {}).get("name", "") + " | " +
             (t.get("away", {}) or {}).get("name", "")).lower()
    return any(top in names for top in tops)

# --- Data-mappings ---
def _load(fn):
    try:
        return json.load(open(os.path.join(DATA, fn), encoding="utf-8"))
    except Exception:
        return {}

TID_SLUG   = _load("tid_slug.json")            # API team-id -> website club-slug
CLUB_NAME  = _load("club_name_slug_filled.json")  # clubnaam -> slug (gevulde clubs)
LANDEN_NL  = _load("landen_nl.json")           # Engelse API-landnaam -> Nederlandse naam

def nl_name(name):
    """Vertaal een landenteam-naam naar het Nederlands (clubs blijven ongemoeid)."""
    return LANDEN_NL.get(name, name)

def club_slug(team_id, name=None):
    """Website-slug voor een club op basis van API team-id (val terug op naam)."""
    s = TID_SLUG.get(str(team_id))
    if s:
        return s
    if name and name in CLUB_NAME:
        return CLUB_NAME[name]
    return None

# Blessure-redenen NL
REASON_NL = {
    "Broken Leg": "beenbreuk", "Leg Injury": "beenblessure", "Knee Injury": "knieblessure",
    "Ankle Injury": "enkelblessure", "Muscle Injury": "spierblessure", "Hamstring": "hamstringblessure",
    "Thigh Injury": "dijblessure", "Groin Injury": "liesblessure", "Calf Injury": "kuitblessure",
    "Hamstring Injury": "hamstringblessure", "Foot Injury": "voetblessure",
    "Back Injury": "rugblessure", "Shoulder Injury": "schouderblessure", "Knock": "lichte blessure",
    "Illness": "ziekte", "Suspended": "schorsing", "Red Card": "schorsing (rode kaart)",
    "Inactive": "niet inzetbaar", "Injury": "blessure", "Coach's decision": "keuze trainer",
    "National selection": "interlandverplichting", "Rest": "rust",
}
_REASON_KW = [("hamstring", "hamstringblessure"), ("ankle", "enkelblessure"), ("knee", "knieblessure"),
               ("calf", "kuitblessure"), ("thigh", "dijblessure"), ("groin", "liesblessure"), ("achilles", "achillespeesblessure"),
               ("foot", "voetblessure"), ("toe", "teenblessure"), ("back", "rugblessure"), ("shoulder", "schouderblessure"),
               ("hip", "heupblessure"), ("concussion", "hersenschudding"), ("head", "hoofdblessure"), ("wrist", "polsblessure"),
               ("hand", "handblessure"), ("muscle", "spierblessure"), ("ill", "ziekte"), ("sick", "ziekte"),
               ("suspen", "schorsing"), ("red card", "schorsing (rode kaart)"), ("yellow", "schorsing (gele kaarten)")]
def reason_nl(r):
    if not r: return "blessure"
    if r in REASON_NL: return REASON_NL[r]
    low = r.lower()
    for kw, nl in _REASON_KW:
        if kw in low:
            return nl
    return "blessure" if re.search(r"[a-z]", low) and not re.search(r"blessure|ziek|schors", low) else low
