# -*- coding: utf-8 -*-
"""Nieuwe/bijgewerkte URL's direct aanmelden bij IndexNow (Bing, Yandex, Seznam e.a.).
De sleutel is openbaar (zo werkt IndexNow) en staat op https://www.bet-experts.nl/<KEY>.txt (Cloudflare-worker
'indexnow-key'). Google doet niet mee aan IndexNow; die vindt de pagina via de sitemap en interne links."""
import json, urllib.request

KEY = "2579388e378e84e49607c8ecf31d96fa"
HOST = "www.bet-experts.nl"


def ping(urls):
    urls = [u for u in dict.fromkeys(urls) if u.startswith(f"https://{HOST}/")]
    if not urls:
        return
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"IndexNow: {len(urls)} URL('s) aangemeld (HTTP {r.status})")
    except Exception as e:
        print(f"IndexNow mislukt: {e}")
