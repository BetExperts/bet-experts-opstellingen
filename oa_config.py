# -*- coding: utf-8 -*-
"""Configuratie voor de opstellingen-agent."""
import os, json

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
LEAGUES = [
    {"worker_slug": "eredivisie",     "comp_slug": "eredivisie",              "naam": "Eredivisie",
     "comp_id": "65de2f987de877fdf6583d10"},
    {"worker_slug": "eerste-divisie", "comp_slug": "keuken-kampioen-divisie", "naam": "Keuken Kampioen Divisie",
     "comp_id": "65de4bc0a8777b9898d6374e"},
]

# --- Data-mappings ---
def _load(fn):
    try:
        return json.load(open(os.path.join(DATA, fn), encoding="utf-8"))
    except Exception:
        return {}

TID_SLUG   = _load("tid_slug.json")            # API team-id -> website club-slug
CLUB_NAME  = _load("club_name_slug_filled.json")  # clubnaam -> slug (gevulde clubs)

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
def reason_nl(r):
    if not r: return "blessure"
    return REASON_NL.get(r, r.lower())
