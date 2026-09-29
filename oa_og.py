# -*- coding: utf-8 -*-
"""Deelafbeelding per opstellingen-artikel (veld met formaties, 'Verwacht' of 'Definitief').

  make(ctx, cfg, slug) -> 'og/<slug>-<hash>.webp' (of None bij een fout; het artikel gaat gewoon door)

De workflow commit het bestand; attach_og.py zet daarna de raw-GitHub-URL in 'afbeelding' en
'seo-afbeelding'. Bij de flip naar definitief komt er een nieuwe afbeelding (echte formaties).
Onbekende formatie -> standaard 4-3-3 (thuis) / 4-2-3-1 (uit).
"""
import hashlib, os

BASE = os.path.dirname(os.path.abspath(__file__))
OG_DIR = os.path.join(BASE, "og")
RAW = "https://raw.githubusercontent.com/BetExperts/bet-experts-opstellingen/main/"

def _cap(s):
    return (s[:1].upper() + s[1:]) if s else s

def info_from(ctx, cfg):
    import og_image as O
    national = bool(cfg.get("landen"))
    ronde = None if (cfg.get("geen_ronde") or cfg.get("vriendschappelijk")) else ctx.get("ronde_txt")
    return {
        "comp": _cap(cfg.get("naam")), "ronde": (ronde[:1].lower() + ronde[1:]) if ronde else None,
        "home": ctx["homeN"], "away": ctx["awayN"], "dt": ctx["dt"],
        "home_logo": O.team_logo(ctx.get("homeId"), ctx.get("homeApi"), national),
        "away_logo": O.team_logo(ctx.get("awayId"), ctx.get("awayApi"), national),
        "definitief": bool(ctx.get("definitief")),
        "home_formatie": (ctx.get("hLU") or {}).get("formation"),
        "away_formatie": (ctx.get("aLU") or {}).get("formation"),
    }

def make(ctx, cfg, slug):
    try:
        import og_image as O
        data = O.render_opstelling(info_from(ctx, cfg))
    except Exception as e:
        print(f"     ! deelafbeelding overgeslagen: {e}")
        return None
    os.makedirs(OG_DIR, exist_ok=True)
    rel = f"og/{slug}-{hashlib.md5(data).hexdigest()[:6]}.webp"
    open(os.path.join(BASE, rel), "wb").write(data)
    return rel
