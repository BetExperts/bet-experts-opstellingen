# -*- coding: utf-8 -*-
"""Externe vermoedelijke elf (alleen namen) -> spelers zoals API-Football ze kent (id, rugnummer, positie, grid).

opstellingvandaag.nl geeft de namen op volgorde van het veld (keeper, verdediging, middenveld, aanval);
FootyMetrics niet (willekeurige volgorde, soms zonder keeper). Daarom zoeken we elke naam op in de laatste
opstellingen van de ploeg (basis + wissels): dat levert positie en rugnummer, en een volledige naam
('Silić' -> 'T. Silić'). Zonder betrouwbare volgorde groeperen we op positie (K, V, M, A).

  build(names, formation, pool, ordered) -> (startXI, formation) of (None, None) als het niet klopt
  pool_from(lineups)                     -> spelerslijst uit API-opstellingen
  line_text(startXI)                     -> 'K; V, V, V, V; M, M, M; A, A, A'
"""
import difflib, re, unicodedata

POS_ORDER = {"G": 0, "D": 1, "M": 2, "F": 3}


def fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _surname(s):
    """'T. ter Stegen' -> 'ter stegen' (voorletters weg)."""
    toks = [t for t in fold(s).split() if len(t) > 1]
    return " ".join(toks)


def _score(src, cand):
    a, b = fold(src), fold(cand)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = _surname(src), _surname(cand)
    if sa and sb and (sa == sb or b.endswith(" " + sa) or a.endswith(" " + sb)):
        # voorletter tegenstrijdig? ('G. Sudakov' vs 'H. Sudakov' is waarschijnlijk dezelfde, iets lager)
        ia, ib = a.split()[0][0], b.split()[0][0]
        return 0.95 if ia == ib or len(a.split()) == 1 or len(b.split()) == 1 else 0.9
    return difflib.SequenceMatcher(None, sa or a, sb or b).ratio() * 0.95


def pool_from(lineups):
    """Alle spelers uit recente opstellingen (recentste eerst), uniek op id. 'row' = laatst bekende rij
    in een basiself (hoger = verder naar voren), voor het verdelen van middenvelders over linies."""
    seen, out = {}, []
    for lu in lineups or []:
        for grp in ("startXI", "substitutes"):
            for pp in lu.get(grp) or []:
                p = pp.get("player") or {}
                key = p.get("id") or p.get("name")
                g = str(p.get("grid") or "")
                row = int(g.split(":")[0]) if grp == "startXI" and re.fullmatch(r"\d+:\d+", g) else None
                if key in seen:
                    if seen[key].get("row") is None and row:
                        seen[key]["row"] = row
                    continue
                if key:
                    seen[key] = {"id": p.get("id"), "name": p.get("name") or "", "number": p.get("number"),
                                 "pos": (p.get("pos") or "").upper()[:1], "row": row}
                    out.append(seen[key])
    return out


def _match(names, pool, verwacht=None):
    """Beste unieke koppeling naam -> pool-speler (of None). verwacht = positie per naam (G/D/M/F) als die bekend
    is: bij gelijke namen (García = Joan García de keeper of Eric García de verdediger) wint de juiste positie."""
    def sc(i, n, p):
        s = _score(n, p["name"])
        if verwacht and verwacht[i] and p.get("pos") == verwacht[i]:
            s += 0.02
        return s
    pairs = sorted(((sc(i, n, p), i, j) for i, n in enumerate(names) for j, p in enumerate(pool)),
                   reverse=True)
    got, used = {}, set()
    for sc, i, j in pairs:
        if sc < 0.84:
            break
        if i in got or j in used:
            continue
        got[i] = pool[j]; used.add(j)
    return [got.get(i) for i in range(len(names))]


def _valid_formation(f):
    return bool(re.fullmatch(r"\d(-\d){1,4}", f or "")) and sum(int(x) for x in f.split("-")) == 10


def build(names, formation, pool, ordered):
    """ordered=True: namen staan op veldvolgorde, per linie van links naar rechts (opstellingvandaag).
    API-Football telt binnen een linie van rechts naar links, dus spiegelen we elke linie."""
    names = [n.strip() for n in names or [] if n and n.strip()]
    if len(names) != 11:
        return None, None
    rijen0 = [1] + [int(x) for x in formation.split("-")] if _valid_formation(formation) else None
    verwacht = None
    if ordered and rijen0:
        verwacht = []
        for r, k in enumerate(rijen0, 1):
            verwacht += ["G" if r == 1 else "D" if r == 2 else "F" if r == len(rijen0) else "M"] * k
    hits = _match(names, pool, verwacht)
    spelers = []
    for n, h in zip(names, hits):
        spelers.append({"id": (h or {}).get("id"), "name": (h or {}).get("name") or n,
                        "number": (h or {}).get("number"), "pos": (h or {}).get("pos") or "",
                        "_row": (h or {}).get("row")})
    rijen = [1] + [int(x) for x in formation.split("-")] if _valid_formation(formation) else None
    if ordered and rijen:
        i = 0
        for r, k in enumerate(rijen, 1):
            linie = spelers[i:i + k]; i += k
            for c, p in enumerate(reversed(linie), 1):
                p["grid"] = f"{r}:{c}"
                p["pos"] = "G" if r == 1 else "D" if r == 2 else "F" if r == len(rijen) else "M"
        spelers.sort(key=lambda p: tuple(int(x) for x in p["grid"].split(":")))
        return [{"player": _clean(p)} for p in spelers], formation
    # geen betrouwbare volgorde: op positie (uit de eigen API-data) groeperen
    nodig = None
    if rijen and len(rijen) >= 3:
        nodig = {"G": 1, "D": rijen[1], "M": sum(rijen[2:-1]), "F": rijen[-1]}
    for p in spelers:                              # onbekende spelers naar de linie die tekortkomt
        if not p["pos"]:
            tekort = [x for x in "GDMF" if nodig and sum(q["pos"] == x for q in spelers) < nodig[x]]
            p["pos"] = tekort[0] if tekort else "M"
    if sum(p["pos"] == "G" for p in spelers) != 1:
        return None, None                          # geen (of twee) keepers: deze voorspelling niet gebruiken
    tel = {x: sum(p["pos"] == x for p in spelers) for x in "GDMF"}
    if nodig and tel == nodig:
        # formatie klopt: middenvelders over de middenlinies verdelen, verdedigend -> aanvallend
        lijnen = {x: [p for p in spelers if p["pos"] == x] for x in "GDF"}
        mid = sorted([p for p in spelers if p["pos"] == "M"], key=lambda p: p["_row"] or 99)
        indeling, i = [lijnen["G"], lijnen["D"]], 0
        for k in rijen[2:-1]:
            indeling.append(mid[i:i + k]); i += k
        indeling.append(lijnen["F"])
        f = formation
    else:
        indeling = [[p for p in spelers if p["pos"] == x] for x in "GDMF"]
        indeling = [l for l in indeling if l]
        f = "-".join(str(len(l)) for l in indeling[1:])
    out = []
    for r, linie in enumerate(indeling, 1):
        for c, p in enumerate(linie, 1):
            p["grid"] = f"{r}:{c}"; out.append({"player": _clean(p)})
    return out, f


def _clean(p):
    return {k: v for k, v in p.items() if not k.startswith("_")}


def line_text(xi, esc=lambda s: s):
    rows = {}
    for pp in xi:
        p = pp["player"]; r, c = (int(x) for x in p["grid"].split(":"))
        rows.setdefault(r, []).append((c, p["name"]))
    return "; ".join(", ".join(esc(n) for _, n in sorted(rows[r])) for r in sorted(rows))
