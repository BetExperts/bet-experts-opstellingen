# -*- coding: utf-8 -*-
"""Dunne wrapper rond de Bet-Experts API-proxy (Cloudflare Worker)."""
import json, time, urllib.request, urllib.error
from oa_config import API

def _get(path):
    url = f"{API}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "opstellingen-agent/1.0", "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1)); continue
            return None
        except Exception:
            time.sleep(2);
    return None

def fixtures(worker_slug):
    """{recent:[...], upcoming:[...]}"""
    d = _get(f"fixtures/{worker_slug}") or {}
    return (d.get("response") or {})

def match(fixture_id):
    d = _get(f"match/{fixture_id}") or {}
    r = d.get("response") or []
    return r[0] if r else None

def lineups(fixture_id):
    d = _get(f"match/{fixture_id}/lineups") or {}
    return d.get("response") or []

def team_form(team_id):
    d = _get(f"team-form/{team_id}") or {}
    return d.get("response") or []

def predictions(fixture_id):
    d = _get(f"predictions/{fixture_id}") or {}
    r = d.get("response") or []
    if isinstance(r, list):
        return r[0] if r else {}
    return r or {}

def h2h(t1, t2):
    d = _get(f"h2h/{t1}-{t2}") or {}
    return d.get("response") or []

def injuries_team(team_id):
    d = _get(f"injuries/team/{team_id}") or {}
    return d.get("response") or []

def coach(team_id):
    d = _get(f"coach/{team_id}") or {}
    r = d.get("response") or []
    return r[0] if r else None
