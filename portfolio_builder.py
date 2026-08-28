#!/usr/bin/env python3
"""
Portfolio / Pipeline-Aggregator für die "Gesamtübersicht" (v1).

Konsolidiert die volle Pipeline Lab -> Shadow -> Demo-Bot -> Live aus vorhandenen Quellen:
  - catalog.json            (Strategy-Lab: Backtest-Kennzahlen pro validierter Strategie)
  - shadow_portfolio.json   (sie generierte Seite: Shadow + Deployed-Mirror je Strategie)
  - deploy_registry.json    (zentrale Lab->Shadow->Bot-Registry: Bot-Mapping + Konten)
  - botN_trades.jsonl       (echte Bot-Trades, für Registry-vs-Real Divergenz-Check)

Schreibt: /root/.hermes/site/api/strategy-lab/portfolio.json und api/portfolio.json (identisch).

Der "Live-Reife-Score" (0-100) ist ADVISORY (Vorschlag), kein automatisches Deploy-Urteil.
Es wird NIEMALS etwas deployed — nur vorgeschlagen.
"""
import json, os, sys
from collections import defaultdict
from datetime import datetime, timezone
import sqlite3

# Trade-Paritäts-Tool (bot ↔ shadow Paar-Matching) als Modul importierbar machen
sys.path.insert(0, "/root/fx-bot/tools")
try:
    from bot_shadow_parity import compute_bot_parity
    HAS_PARITY = True
except Exception as _e:  # pragma: no cover
    print(f"  [warn] bot_shadow_parity: {_e}", file=sys.stderr)
    HAS_PARITY = False

SITE_API = "/root/.hermes/site/api"

def norm(x):
    return str(x or "").strip().lstrip("#")

def load(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception as e:
        print(f"  [warn] {p}: {e}", file=sys.stderr)
        return default

DESCRIPTIONS = load(f"{os.path.dirname(os.path.abspath(__file__))}/portfolio_descriptions.json", {}) or {}

def describe(sid, lab_name):
    """Liefert plakative Beschreibung (was/gut/nicht + tag + ausmacht/ergaenzt) für eine Strategie.
    Prio: (1) Override nach ID, (2) erster Approach-Match im lowercased Namen."""
    name_l = (lab_name or "").lower()
    overrides = DESCRIPTIONS.get("overrides", {}) or {}
    if str(sid) in overrides:
        o = overrides[str(sid)]
        return {"tag": o.get("tag") or "Individuell",
                "was": o.get("was", ""), "gut": o.get("gut", ""), "nicht": o.get("nicht", ""),
                "ausmacht": o.get("ausmacht", ""), "ergaenzt": o.get("ergaenzt", "")}
    for a in DESCRIPTIONS.get("approaches", []) or []:
        for kw in a.get("match", []) or []:
            if kw in name_l or kw in sid:
                return {"tag": a.get("tag"), "was": a.get("was", ""),
                        "gut": a.get("gut", ""), "nicht": a.get("nicht", ""),
                        "ausmacht": a.get("ausmacht", ""), "ergaenzt": a.get("ergaenzt", "")}
    return {"tag": "Unklar", "was": "", "gut": "", "nicht": "", "ausmacht": "", "ergaenzt": ""}

def load_bot_trades():
    out = {}
    for n in range(1, 6):
        p = f"/root/fx-bot/data/bot{n}_trades.jsonl"
        rows = []
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
        ctr = defaultdict(int)
        for r in rows:
            ctr[norm(r.get("strategy_id"))] += 1
        open_n = sum(1 for r in rows if str(r.get("status")) == "open")
        last_sid = norm(rows[-1].get("strategy_id")) if rows else None
        out[f"bot{n}"] = {
            "count": len(rows),
            "strategy_ids": dict(ctr),
            "last_strategy": last_sid,
            "open": open_n,
        }
    return out

def load_catalog_names():
    """Holt den echten Strategie-Namen (Recipe) aus catalog.db — Quelle der Wahrheit."""
    names = {}
    try:
        conn = sqlite3.connect("/root/strategy-lab/catalog.db")
        for row in conn.execute("SELECT id, name FROM strategies"):
            names[str(row[0])] = row[1]
        conn.close()
    except Exception as e:
        print(f"  [warn] catalog.db Namen: {e}", file=sys.stderr)
    return names

def compute_ready(lab, shadow, deployed, is_deployed, parity):
    """Advisory Live-Reife-Score 0-100 mit klar deklarierten Checks."""
    score = 0
    checks = []
    # 1. Lab-Backtest-Qualität
    lab_score = lab.get("score") if lab else None
    if lab_score is not None and lab_score >= 50:
        score += 20
        checks.append({"ok": True, "label": "Lab-Score ≥ 50"})
    else:
        checks.append({"ok": False, "label": f"Lab-Score {'%s' % lab_score if lab_score is not None else 'n.a.'} < 50"})
    # 2. Shadow-Live (Forward-Test)
    tr = (shadow.get("trades") or 0) if shadow else 0
    eq = (shadow.get("equity") or 1000) if shadow else 1000
    if tr >= 5 and eq > 1000:
        score += 30
        checks.append({"ok": True, "label": f"Shadow ≥5 Trades & positiv ({eq:.0f}€)"})
    else:
        checks.append({"ok": False, "label": f"Shadow {'%d' % tr}-T, Equity {eq:.0f}€ (nicht reif)"})
    # 3. Demo-Bot deployed + Registry-Parität
    if parity and is_deployed:
        score += 30
        checks.append({"ok": True, "label": "Demo-Bot & Registry-abgeglichen"})
        if deployed and deployed.get("trades", 0) >= 3:
            score += 10
            checks.append({"ok": True, "label": "Bot ≥3 Trades"})
        else:
            checks.append({"ok": False, "label": "Bot <3 Trades"})
    else:
        checks.append({"ok": False, "label": "Kein abgeglichener Demo-Bot"})
    # 4. Win-Rate
    wr = shadow.get("wr") if shadow else None
    if wr is not None and wr >= 50:
        score += 10
        checks.append({"ok": True, "label": "WR ≥ 50%"})
    else:
        checks.append({"ok": False, "label": f"WR {'%s' % wr} < 50%"})
    # 5. Gap (Shadow besser als OOS-Referenz)
    gap = shadow.get("gap_pct") if shadow else None
    if gap is not None and gap >= 0:
        score += 10
        checks.append({"ok": True, "label": "Gap ≥ 0"})
    else:
        checks.append({"ok": False, "label": f"Gap {'%s' % gap} < 0"})
    return {"score": min(100, score), "checks": checks, "is_ready": score >= 80}

def compute_bot_rec(shadow, lab, is_deployed):
    """🚀 Bot-Eignung (0-100) — bewertet eine Shadow-Strategie rein anhand ihrer
    Forward-Test-Qualität, UNABHÄNGIG davon ob schon ein Bot existiert.
    So kann man reine Shadow-Kandidaten sinnvoll für den nächsten Bot-Slot vergleichen.
    Vergleichbar mit compute_ready, aber ohne 'Bot existiert'-Punkte."""
    score = 0
    checks = []
    if not shadow or shadow.get("trades") is None:
        return {"score": 0, "level": "niedrig", "checks": [{"ok": False, "label": "Noch keine Shadow-Trades"}], "hint": "Erst Handel im Shadow abwarten."}
    tr = shadow.get("trades") or 0
    eq = shadow.get("equity") or 1000
    wr = shadow.get("wr")
    wpw = shadow.get("pnl_per_week")
    gap = shadow.get("gap_pct")
    oos_pf = shadow.get("oos_pf")
    # 1. Shadow-Trades + Profitabilität (Forward-Test)
    if tr >= 5 and eq > 1000:
        score += 35
        checks.append({"ok": True, "label": f"≥5 Shadow-Trades & positiv ({eq:.0f}€)"})
    elif tr >= 1:
        checks.append({"ok": False, "label": f"Nur {tr} Trades / Equity {eq:.0f}€"})
    else:
        checks.append({"ok": False, "label": "Keine Shadow-Trades"})
    # 2. Win-Rate
    if wr is not None and wr >= 50:
        score += 25
        checks.append({"ok": True, "label": f"WR ≥ 50% ({wr:.0f}%)"})
    else:
        checks.append({"ok": False, "label": f"WR {'%s' % wr if wr is not None else 'n.a.'} < 50%"})
    # 3. €/Woche (Frequency × Größe)
    if wpw is not None and wpw >= 10:
        score += 20
        checks.append({"ok": True, "label": f"€/Woche ≥ 10 ({wpw:.0f}€)"})
    elif wpw is not None and wpw > 0:
        score += 10
        checks.append({"ok": True, "label": f"€/Woche positiv ({wpw:.0f}€)"})
    else:
        checks.append({"ok": False, "label": f"€/Woche {'%s' % wpw if wpw is not None else 'n.a.'} nicht positiv"})
    # 4. Lab-Backtest (OOS PF)
    if oos_pf is not None and oos_pf >= 1.2:
        score += 10
        checks.append({"ok": True, "label": f"OOS PF ≥ 1.2 ({oos_pf:.2f})"})
    else:
        checks.append({"ok": False, "label": f"OOS PF {'%s' % oos_pf if oos_pf is not None else 'n.a.'}"})
    # 5. Gap (Shadow hält OOS-Versprechen)
    if gap is not None and gap >= 0:
        score += 10
        checks.append({"ok": True, "label": "Gap ≥ 0 (kein Abfall)"})
    else:
        checks.append({"ok": False, "label": f"Gap {'%s' % gap if gap is not None else 'n.a.'}"})

    score = min(100, score)
    level = "hoch" if score >= 70 else ("mittel" if score >= 45 else "niedrig")
    hint = ""
    if is_deployed:
        hint = "Läuft bereits auf einem Demo-Bot."
    elif level == "hoch":
        hint = "Starker Kandidat für einen freien Bot-Slot."
    elif level == "mittel":
        hint = "Solide — mehr Shadow-Trades abwarten."
    else:
        hint = "Noch nicht reif — erst Shadow weiterlaufen lassen."
    return {"score": score, "level": level, "checks": checks, "hint": hint, "already_deployed": is_deployed}

def compute_live_rec(shadow, deployed, mirror, is_deployed, trade_parity):
    """💳 Live-Bereitschaft (0-100) — bewertet NUR bereits deployed Demo-Bots auf ihre
    Eignung für Echtgeld. Strenger als bot_rec: braucht reale Shadow↔Bot-Trade-Parität,
    längeren Demo-Test-Record und keine Konsistenz-Lücken. Kein einzelner Faktor reicht.

    trade_parity: dict aus bot_shadow_parity.compute_bot_parity (matched_pairs, status …).
    Harte Blocker (→ 0, "hochrisiko", NICHT auf Echtgeld):
      - needs_smoke_test : 0 gematchte Paare (nach Umstellung erst ersten Testrade prüfen)
      - abweichung       : gematchte Paare mit Entry/SL/TP-Divergenz zum Shadow
    """
    if not is_deployed:
        return {"score": 0, "level": "kein Bot", "checks": [{"ok": False, "label": "Kein Demo-Bot deployed"}], "hint": "Erst auf Demo testen."}

    tp = trade_parity or {}
    p_status = tp.get("status")
    p_matched = tp.get("matched_pairs") or 0
    p_entry = tp.get("entry_ok") or 0
    p_rate = tp.get("match_rate") or 0.0

    # 0. Harte Blocker: Parität unzureichend
    if p_status == "needs_smoke_test":
        return {"score": 0, "level": "hochrisiko",
                "checks": [{"ok": False, "label": "Noch 0 gematchte Paare — Smoke-Test offen"},
                           {"ok": False, "label": "Erst Testrade abwarten (Skalierung / SL / TP prüfen)"}],
                "hint": "Bot hat nach Umstellung noch keinen gegen den Shadow verifizierten Trade."}
    if p_status == "abweichung":
        return {"score": 0, "level": "hochrisiko",
                "checks": [{"ok": False, "label": f"Shadow↔Bot-Divergenz: {p_matched} Paare, Entry ok {p_entry}, Rate {p_rate:.0%}"},
                           {"ok": False, "label": "Entry/SL/TP weichen vom Shadow ab — erst beheben"}],
                "hint": "Bot handelt NICHT wie der Shadow (SL/TP/Entry-Drift). NICHT auf Echtgeld."}

    score = 0
    checks = []
    # 1. Trade-Parität Shadow ↔ Bot (echtes Paar-Matching)
    if p_status == "paritaet":
        score += 20
        checks.append({"ok": True, "label": f"Parität bestätigt: {p_matched} gematchte Paare, Entry-Rate {p_rate:.0%}"})
    else:  # sammlung — Paare vorhanden, aber noch < MIN_MATCHED_PAIRS
        pt = "geprüft" if p_matched >= 5 else "im Aufbau"
        score += 8
        checks.append({"ok": False, "label": f"Parität {pt}: {p_matched} von min 10 Paare, Rate {p_rate:.0%}"})
    # 2. Demo-Test-Record (Trades + Equity)
    m = mirror or {}
    m_tr = m.get("trades") or 0
    m_eq = m.get("equity") or 0
    if m_tr >= 5 and m_eq > 1000:
        score += 30
        checks.append({"ok": True, "label": f"Demo ≥5 Trades & positiv ({m_eq:.0f}€)"})
    else:
        checks.append({"ok": False, "label": f"Demo nur {m_tr} Trades / {m_eq:.0f}€"})
    # 3. Shadow-Stabilität (Forward, unterlegt)
    s_tr = (shadow.get("trades") or 0) if shadow else 0
    s_eq = (shadow.get("equity") or 1000) if shadow else 1000
    if s_tr >= 10 and s_eq > 1000:
        score += 25
        checks.append({"ok": True, "label": f"Shadow ≥10 Trades & stabil ({s_eq:.0f}€)"})
    else:
        checks.append({"ok": False, "label": f"Shadow {s_tr} Trades / {s_eq:.0f}€"})
    # 4. Win-Rate
    wr = mirror.get("wr") if mirror else None
    if wr is not None and wr >= 50:
        score += 15
        checks.append({"ok": True, "label": f"WR ≥ 50% ({wr:.0f}%)"})
    else:
        checks.append({"ok": False, "label": f"WR {'%s' % wr if wr is not None else 'n.a.'}"})
    # 5. Lab-Backtest + Gap (hold Versprechen)
    oos_pf = shadow.get("oos_pf") if shadow else None
    gap = shadow.get("gap_pct") if shadow else None
    if oos_pf is not None and oos_pf >= 1.2:
        score += 10
        checks.append({"ok": True, "label": f"OOS PF ≥ 1.2 ({oos_pf:.2f})"})
    else:
        checks.append({"ok": False, "label": f"OOS PF {'%s' % oos_pf if oos_pf is not None else 'n.a.'}"})
    score = min(100, score)
    level = "bereit" if score >= 80 else ("nah_ran" if score >= 60 else "abwarten")
    hint = ("Starker Kandidat für Echtgeld." if level == "bereit"
            else ("Fast bereit — noch etwas Demo-Track aufbauen." if level == "nah_ran"
            else "Noch nicht: mehr Demo- oder Shadow-Konsistenz abwarten."))
    return {"score": score, "level": level, "checks": checks, "hint": hint}

def main():
    catalog = load(f"{SITE_API}/strategy-lab/catalog.json") or {}
    shadow_pf = load(f"{SITE_API}/strategy-lab/shadow_portfolio.json") or {}
    deploy_reg = load("/root/fx-bot/config/deploy_registry.json") or {}
    selected = load("/root/fx-bot/data/shadow/selected_ids.json") or []

    deploy_list = catalog.get("deploy", [])
    catalog_deploy_by_id = {norm(s.get("id")): s for s in deploy_list}

    # Bot-Mapping aus Registry
    bots = deploy_reg.get("bots", {})                 # {botN: {...}}
    shadow_mapping = deploy_reg.get("shadow_mapping", {})   # {"194": {bot:"bot4"...}}
    strat_to_bot = {norm(sid): m.get("bot") for sid, m in shadow_mapping.items()}

    # Shadow-Portfolio: pure Einträge + Mirrors
    shadow_by_id = {}
    mirrors_by_sid = defaultdict(list)
    for s in shadow_pf.get("strategies", []):
        raw = s.get("id")
        if raw is None:
            continue
        key = str(raw)
        if "@" in key:
            base, _, bot = key.partition("@")
            mirrors_by_sid[norm(base)].append({**s, "_bot": bot})
        else:
            shadow_by_id[norm(key)] = s
    for v in mirrors_by_sid.values():
        v.sort(key=lambda m: m.get("_bot") or "")

    # Echte Bot-Trades
    bot_trades = load_bot_trades()
    # Echte Strategie-Namen (Recipe) aus catalog.db
    cat_names = load_catalog_names()

    # Union der Strategie-IDs
    all_ids = set(shadow_by_id) | set(mirrors_by_sid) | {norm(x) for x in selected} | set(catalog_deploy_by_id)

    strategies = []
    for sid in sorted(all_ids, key=lambda x: (len(x), x)):
        ns = norm(sid)
        shadow_entry = shadow_by_id.get(ns) or {}
        mirror_list = mirrors_by_sid.get(ns, [])
        lab_row = catalog_deploy_by_id.get(ns)
        assigned_bot = strat_to_bot.get(ns)
        is_deployed = bool(mirror_list)
        is_selected = ns in {norm(x) for x in selected}

        # Divergenz-Check: letzter Trade des zugewiesenen Bots
        live_strat = None
        divergence = False
        if assigned_bot and bot_trades.get(assigned_bot):
            bt = bot_trades[assigned_bot]
            live_strat = bt["last_strategy"]
            if live_strat:
                divergence = (live_strat != ns)

        # Lab-Metrik
        lab = None
        if lab_row:
            lab = {
                "pf": lab_row.get("pf"),
                "trades": lab_row.get("trades"),
                "pnl_month": lab_row.get("pnl_per_month"),
                "tier": lab_row.get("tier"),
                "score": lab_row.get("score"),
                "pass_rate": lab_row.get("pass_rate"),
                "fire_test": lab_row.get("fire_test"),
                "gates": lab_row.get("gates"),
                "timeframe": lab_row.get("timeframe"),
                "assets": lab_row.get("assets") or [],
            }
        else:
            # Fallback: aus Shadow (oo_*)
            lab = {
                "pf": shadow_entry.get("oos_pf"),
                "trades": shadow_entry.get("oos_trades"),
                "pnl_month": shadow_entry.get("pnl_per_month"),
                "tier": None, "score": None, "pass_rate": None,
                "fire_test": None, "gates": None,
                "timeframe": shadow_entry.get("timeframe"),
                "assets": shadow_entry.get("symbols") or [],
            }

        shadow_metric = {
            "equity": shadow_entry.get("equity"),
            "pnl": shadow_entry.get("net_pnl"),
            "trades": shadow_entry.get("trades"),
            "wr": shadow_entry.get("win_rate"),
            "pnl_per_week": shadow_entry.get("pnl_per_week"),
            "days": shadow_entry.get("days_active"),
            "symbols": shadow_entry.get("symbols") or (lab.get("assets") if lab else []),
            "gap_pct": shadow_entry.get("gap_pct"),
            "oos_pf": shadow_entry.get("oos_pf"),
        }

        deployed_metric = None
        if mirror_list:
            m = mirror_list[0]
            deployed_metric = {
                "equity": m.get("equity"),
                "pnl": m.get("net_pnl"),
                "trades": m.get("trades"),
                "wr": m.get("win_rate"),
                "pnl_per_week": m.get("pnl_per_week"),
                "days": m.get("days_active"),
                "bot": m.get("_bot"),
            }

        # 🔀 Echte Trade-Parität Shadow ↔ Bot (nur für deployed Bots)
        trade_parity = None
        if is_deployed and assigned_bot and HAS_PARITY:
            try:
                trade_parity = compute_bot_parity(assigned_bot)
            except Exception as _e:
                print(f"  [warn] Parität {assigned_bot}: {_e}", file=sys.stderr)
                trade_parity = None

        flags = {
            "has_shadow": bool(shadow_entry or mirror_list),
            "has_demo_bot": bool(mirror_list),
            "parity": is_deployed and assigned_bot and not divergence,
            "parity_ok": bool(trade_parity and trade_parity.get("status") in ("sammlung", "paritaet")),
            "selected_shadow": is_selected,
        }

        ready = compute_ready(lab, shadow_metric, deployed_metric, is_deployed, flags["parity"])
        # 🚀 Bot-Eignung (individuell, unabhängig von bereits existierendem Bot)
        bot_rec = compute_bot_rec(shadow_metric, lab, is_deployed)
        # 💳 Live-Bereitschaft (nur für deployed Demo-Bots: Echtgeld-Eignung)
        live_rec = compute_live_rec(shadow_metric, deployed_metric, deployed_metric, is_deployed, trade_parity)

        # Assets/Strategie-Namen
        name = lab_row.get("name") if lab_row else f"#{ns}"
        assets = (lab.get("assets") if lab else []) or (shadow_metric.get("symbols") or [])
        # Fallback auf echten Recipe-Namen aus catalog.db (wenn nur #id da)
        if name == f"#{ns}" and cat_names.get(ns):
            name = cat_names[ns]

        # Plakative Beschreibung
        desc = describe(ns, name)

        strategies.append({
            "id": ns,
            "name": name,
            "assets": assets,
            "timeframe": (lab or {}).get("timeframe"),
            "selected_shadow": is_selected,
            "lab": lab,
            "shadow": shadow_metric,
            "bot": {
                "assigned": assigned_bot,
                "deployed": is_deployed,
                "mirror": deployed_metric,
                "live_strategy": live_strat,
                "divergence": divergence,
                "parity": trade_parity,
            },
            "flags": flags,
            "ready": ready,
            "bot_rec": bot_rec,
            "live_rec": live_rec,
            "desc": desc,
        })

    # Sort: deployed first, dann score
    strategies.sort(key=lambda x: (0 if x["flags"]["has_demo_bot"] else 1, -x["ready"]["score"]))

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "portfolio_builder v1 (advisory pipeline uebersicht)",
        "_note": "Advisory -- nur Vorschlaege, kein automatisches Deploy.",
        "bots": {name: {"account_id": b.get("account_id"), "demo": b.get("demo", True)} for name, b in bots.items()},
        "strategy_count": len(strategies),
        "strategies": strategies,
    }

    outs = [f"{SITE_API}/strategy-lab/portfolio.json", f"{SITE_API}/portfolio.json"]
    for out in outs:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"Fertig: {len(strategies)} Strategien -> {outs[0]}")
    print(f"  Demo-Bot belegt: {sum(1 for s in strategies if s['flags']['has_demo_bot'])}")
    print(f"  Divergenzen (Registry vs. real): {sum(1 for s in strategies if s['bot'].get('divergence'))}")

if __name__ == "__main__":
    main()