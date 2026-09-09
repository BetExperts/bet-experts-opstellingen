# -*- coding: utf-8 -*-
"""Genereert de VERMOEDELIJKE opstellingen-artikelen voor een dag (avond ervoor).
  python3 generate.py --date 2026-09-12 --dry      # niks schrijven, alleen tellen
  python3 generate.py --date 2026-09-12 --preview   # HTML-previews wegschrijven
  python3 generate.py --date 2026-09-12             # live aanmaken + publiceren
Zonder --date: morgen (Europe/Amsterdam)."""
import sys, os, argparse
from datetime import datetime, timedelta
import oa_api as api
import oa_match as M
import oa_build as B
from oa_config import LEAGUES, BASE, WEBFLOW_TOKEN
import oa_webflow as WF

def target_date(arg):
    if arg: return arg
    d = B._local(datetime.now().astimezone().isoformat()) + timedelta(days=1)
    return f"{d.year}-{d.month:02d}-{d.day:02d}"

def match_on_date(fx, ymd):
    dt = B._local(fx.get("fixture", {}).get("date"))
    return f"{dt.year}-{dt.month:02d}-{dt.day:02d}" == ymd

def write_preview(fd, title):
    os.makedirs(os.path.join(BASE, "preview"), exist_ok=True)
    p = os.path.join(BASE, "preview", fd["slug"] + ".html")
    html = (f"<title>{title}</title><body style='font-family:system-ui;max-width:760px;margin:24px auto;padding:0 16px'>"
            f"<div style='background:#0F1621;color:#cfe6d8;padding:12px 16px;border-radius:10px;font-size:13px'>"
            f"<b>samenvatting:</b> {fd['samenvatting']}</div>"
            f"<h1 style='font-size:20px'>{title}</h1>"
            f"<div style='border-left:3px solid #12833D;padding-left:14px'><b>content</b>{fd['content']}</div>"
            f"<div style='border-left:3px solid #999;padding-left:14px'><b>content-2</b>{fd['content-2']}</div>"
            f"<div style='border-left:3px solid #999;padding-left:14px'><b>content-3</b>{fd['content-3']}</div></body>")
    open(p, "w", encoding="utf-8").write(html)
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--preview", action="store_true"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    ymd = target_date(a.date)
    live = not (a.dry or a.preview)
    if live and not WEBFLOW_TOKEN:
        print("FOUT: WEBFLOW_TOKEN ontbreekt (of gebruik --dry/--preview)."); sys.exit(1)

    state = WF.load_state()
    print(f"== Genereren voor {ymd} | modus: {'LIVE' if live else ('PREVIEW' if a.preview else 'DRY')} ==")
    made = 0
    for cfg in LEAGUES:
        resp = api.fixtures(cfg["worker_slug"])
        ups = (resp.get("upcoming") or [])
        day = [fx for fx in ups if match_on_date(fx, ymd)]
        print(f"\n{cfg['naam']}: {len(day)} wedstrijd(en) op {ymd}")
        for fx in day:
            fid = str(fx.get("fixture", {}).get("id"))
            if fid in state:
                print(f"  · overslaan (bestaat al): {fid}"); continue
            ctx = M.gather(fx, definitief=False)
            fd, slug, title = M.build_fielddata(ctx, cfg)
            if a.preview:
                p = write_preview(fd, title); print(f"  ✎ preview: {p}")
            elif a.dry:
                print(f"  ○ zou maken: {title}")
            else:
                item_id = WF.create_live(fd)
                state[fid] = {"item_id": item_id, "slug": slug, "definitief": False,
                              "match": f"{ctx['homeN']} - {ctx['awayN']}", "date": ymd,
                              "league": cfg["worker_slug"],
                              "comp_slug": cfg["comp_slug"], "naam": cfg["naam"]}
                WF.save_state(state)
                print(f"  ✔ live: {title}  (item {item_id})")
            made += 1
            if a.limit and made >= a.limit: break
        if a.limit and made >= a.limit: break
    print(f"\nKLAAR — {made} artikel(en) verwerkt.")

if __name__ == "__main__":
    main()
