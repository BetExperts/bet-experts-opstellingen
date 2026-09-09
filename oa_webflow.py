# -*- coding: utf-8 -*-
"""Webflow CMS: aanmaken (+publiceren) en updaten (+publiceren) van items,
plus een lokaal state-bestand fixture-id -> item-id."""
import json, os, time, urllib.request, urllib.error
from oa_config import WEBFLOW_TOKEN, NIEUWS_COLLECTION, WF_API, BASE

STATE = os.path.join(BASE, "state", "opstellingen.json")

def _req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + WEBFLOW_TOKEN)
    r.add_header("accept", "application/json")
    if data: r.add_header("content-type", "application/json")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                body = resp.read().decode().strip()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "5")) + 1); continue
            if e.code >= 500:
                time.sleep(3); continue
            if e.code == 404:
                return {}   # al weg
            raise RuntimeError(f"Webflow HTTP {e.code}: {e.read().decode()[:300]}")
    raise RuntimeError("Webflow: te veel retries")

def create_live(field_data):
    """Maak een item aan EN publiceer het meteen. Retourneert het item-id."""
    body = {"isArchived": False, "isDraft": False, "fieldData": field_data}
    res = _req("POST", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items/live", body)
    # respons kan {id,...} of {items:[{id}]} zijn
    if isinstance(res, dict):
        if res.get("id"): return res["id"]
        items = res.get("items") or []
        if items: return items[0].get("id")
    raise RuntimeError(f"Onverwachte create-respons: {json.dumps(res)[:200]}")

def update_live(item_id, field_data):
    return _req("PATCH", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items/{item_id}/live",
                {"fieldData": field_data})

def delete_item(item_id):
    """Haalt het item van de live site en verwijdert het uit de CMS."""
    try:
        _req("DELETE", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items/{item_id}/live")
    except Exception:
        pass  # was misschien al niet gepubliceerd
    return _req("DELETE", f"{WF_API}/collections/{NIEUWS_COLLECTION}/items/{item_id}")

# ---------- state ----------
def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}

def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
