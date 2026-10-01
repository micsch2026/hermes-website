#!/usr/bin/env python3
"""
test_build_overview.py — Fixture-Tests fuer build_overview_status.py (overview_v1).

Baut tmp-Fixtures (fx/sl/td/site-root): 2 Bots (bot1 voll mit Curve+risk_state,
bot4 "leer": nur balance + leere trades/positions, KEIN risk_state), kleine
shadow-JSONL, rotation_state mit 1 Challenge, spots_all, Mini-catalog.db
(sqlite3, recipes+strategies), Mini risk_guards, pipeline_status.
decay/tca-Subprozess-Funktionen werden monkeypatcht (Fake-Dicts, schreiben
jeweils die Output-Datei — wie der echte Subprozess).

Run:  python3 tests/test_build_overview.py   → alle PASS / exit 1 bei FAIL
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import build_overview_status as m  # noqa: E402

NOW_DT = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)  # Dienstag
NOW = NOW_DT.timestamp()


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def space_ts(dt):
    """'YYYY-MM-DD HH:MM:SS'-Format (UTC) — alternativ zu ISO toleriert."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _touch(path, age_s):
    mt = NOW - age_s
    os.utime(path, (mt, mt))


# ══════════════════════════════════════════════════════════════════════════════
# Fixture-Builder
# ══════════════════════════════════════════════════════════════════════════════

def make_fixture(base, with_empty_bot=True, feed_age_s=60.0):
    fx = os.path.join(base, "fx")
    sl = os.path.join(base, "sl")
    td = os.path.join(base, "td")
    root = os.path.join(base, "root")
    for d in (os.path.join(fx, "config"), os.path.join(fx, "data", "shadow"),
              os.path.join(fx, "data", "rotation"), os.path.join(fx, "scripts"),
              os.path.join(sl, "data"), os.path.join(td, "stream"),
              os.path.join(root, "api", "data"), os.path.join(root, "api", "overview")):
        os.makedirs(d, exist_ok=True)

    # ── fx/config ──
    registry = {"bots": {
        "bot1": {"account_id": 1, "demo": True, "strategy_id": 724, "role": "pipeline"},
        "bot4": {"account_id": 2, "demo": False, "is_live": True, "strategy_id": 317,
                 "role": "live"},
    }}
    _w = lambda p, o: open(p, "w", encoding="utf-8").write(json.dumps(o))
    _w(os.path.join(fx, "config", "deploy_registry.json"), registry)
    _w(os.path.join(fx, "config", "risk_guards.json"),
       {"defaults": {"l1_alert_pct": 3.0, "l2_block_pct": 5.0},
        "bots": {"bot4": {"max_loss_ref": 1000.0}}})
    _w(os.path.join(fx, "config", "rotation_policy.json"),
       {"policy": {"challenge_days": 14},
        "targets": [
            {"bot": "bot1", "asset_class": "FX", "slot_ids": ["s724", "srot"]},
            {"bot": "bot4", "asset_class": "METAL", "slot_ids": ["s317"]},
        ]})
    with open(os.path.join(fx, "config", "bot1_multi.toml"), "w") as fh:
        fh.write('[[slots]]\nid = "s724"\nstrategy_id = 724\n')

    # ── bot1 (voll) ──
    _w(os.path.join(fx, "data", "bot1_balance.json"),
       {"balance": 98234, "money_digits": 2, "equity": 98510, "account_id": "1",
        "updated": iso_z(NOW_DT - timedelta(minutes=1))})
    snaps = []
    eq_vals = [980.0, 981.5, 983.0, 984.5, 985.0]
    for k, eq in enumerate(eq_vals):
        ts = NOW_DT - timedelta(seconds=3600 - k * 750)
        snaps.append({"timestamp": iso_z(ts), "balance": 982.34,
                      "equity": eq, "open_pnl": 0.0, "positions": 1, "margin": 10.0})
    _w(os.path.join(fx, "data", "bot1_balance_history.json"), {"snapshots": snaps})
    _w(os.path.join(fx, "data", "bot1_risk_state.json"),
       {"bot": "bot1", "equity": 985.1, "dd_pct": -2.0, "level": 0, "block": False,
        "is_live": False, "daily": {"pnl_pct": 0.5},
        "updated": iso_z(NOW_DT - timedelta(minutes=1))})
    _w(os.path.join(fx, "data", "bot1_positions_live.json"),
       [{"position_id": "1", "symbol": "EURUSD", "volume": 100000, "entry": 1.17,
         "sl": 1.16, "side": "buy"},
        {"position_id": "2", "symbol": "XAUUSD", "volume": 100, "entry": 3800.0,
         "sl": 3780.0, "side": "buy"}])
    trades1 = [
        {"closed_at": iso_z(NOW_DT - timedelta(days=2)), "cTrader_profit": 7.5,
         "strategy_id": 724, "symbol": "EURUSD"},
        {"closed_at": iso_z(NOW_DT - timedelta(days=5)), "cTrader_profit": 2.0,
         "strategy_id": 724, "symbol": "EURUSD"},
        {"closed_at": space_ts(NOW_DT - timedelta(days=20)), "pnl": 20.0,
         "strategy_id": 724, "symbol": "XAUUSD"},          # Fallback-Feld + Space-Format
        {"closed_at": iso_z(NOW_DT - timedelta(days=40)), "cTrader_profit": 100.0,
         "strategy_id": 724, "symbol": "EURUSD"},          # außerhalb beider Fenster
    ]
    with open(os.path.join(fx, "data", "bot1_trades.jsonl"), "w") as fh:
        for t in trades1:
            fh.write(json.dumps(t) + "\n")

    # ── bot4 ("leer": balance + leere trades/positions, KEIN risk_state) ──
    if with_empty_bot:
        _w(os.path.join(fx, "data", "bot4_balance.json"),
           {"balance": 50000, "money_digits": 2, "account_id": "2",
            "updated": iso_z(NOW_DT - timedelta(minutes=2))})
        open(os.path.join(fx, "data", "bot4_trades.jsonl"), "w").close()
        with open(os.path.join(fx, "data", "bot4_trades.jsonl"), "a") as fh:
            fh.write(json.dumps({"closed_at": space_ts(NOW_DT - timedelta(days=3)),
                                 "pnl": 12.0, "strategy_id": 317, "symbol": "XAUUSD"}) + "\n")
        _w(os.path.join(fx, "data", "bot4_positions_live.json"), [])

    # ── shadow ──
    shadow_rows = [
        {"strategy_id": 724, "net_pnl": 10.0, "exit_ts": NOW - 2 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 2 * 86400 - 60},
        {"strategy_id": 724, "net_pnl": -4.0, "exit_ts": NOW - 10 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 10 * 86400 - 60},
        {"strategy_id": 724, "net_pnl": 2.0, "exit_ts": NOW - 20 * 86400,
         "symbol": "XAUUSD", "entry_ts": NOW - 20 * 86400 - 60},
        {"strategy_id": 724, "net_pnl": 4.0, "exit_ts": NOW - 28 * 86400,
         "symbol": "XAUUSD", "entry_ts": NOW - 28 * 86400 - 60},
        {"strategy_id": 724, "net_pnl": -1.0, "exit_ts": NOW - 45 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 45 * 86400 - 60},   # > 30d
        {"strategy_id": "724@bot1", "net_pnl": 100.0, "exit_ts": NOW - 3 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 3 * 86400 - 60},     # Mirror → skip
        {"strategy_id": 317, "net_pnl": 5.0, "exit_ts": NOW - 2 * 86400,
         "symbol": "XAUUSD", "entry_ts": NOW - 2 * 86400 - 60},
        {"strategy_id": 317, "net_pnl": -2.0, "exit_ts": NOW - 10 * 86400,
         "symbol": "XAUUSD", "entry_ts": NOW - 10 * 86400 - 60},
        {"strategy_id": 317, "net_pnl": 1.0, "exit_ts": NOW - 20 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 20 * 86400 - 60},
        {"strategy_id": 317, "net_pnl": 2.0, "exit_ts": NOW - 28 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 28 * 86400 - 60},
        {"strategy_id": 999, "net_pnl": 50.0, "exit_ts": NOW - 40 * 86400,
         "symbol": "EURUSD", "entry_ts": NOW - 40 * 86400 - 60},
    ]
    with open(os.path.join(fx, "data", "shadow", "shadow_trades.jsonl"), "w") as fh:
        for r in shadow_rows:
            fh.write(json.dumps(r) + "\n")

    # ── rotation ──
    _w(os.path.join(fx, "data", "rotation", "rotation_state.json"),
       {"slots": {
           "s724": {"holder": 724},
           "srot": {"holder": None,
                    "challenge": {"candidate": 999,
                                  "started": iso_z(NOW_DT - timedelta(days=7))}},
           "s317": {"holder": 317},
       }})

    # ── spots (Feed) ──
    _w(os.path.join(td, "stream", "spots_all.json"),
       {"EURUSD": {"bid": 1.17, "ask": 1.1702, "spread": 0.0002,
                   "timestamp": iso_z(NOW_DT - timedelta(seconds=feed_age_s))},
        "XAUUSD": {"bid": 3800.0, "ask": 3800.4, "spread": 0.4,
                   "timestamp": iso_z(NOW_DT - timedelta(seconds=feed_age_s + 60))}})

    # ── strategy-lab ──
    _w(os.path.join(sl, "data", "worker_status.json"),
       {"status": "recipe_running", "strategy_type": "fx_grid", "elapsed_s": 42,
        "message": "cluster X läuft", "updated_at": iso_z(NOW_DT - timedelta(minutes=1))})
    db_path = os.path.join(sl, "catalog.db")
    if os.path.exists(db_path):
        os.unlink(db_path)
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE strategies (id INTEGER PRIMARY KEY, name TEXT, "
                "wfo_result TEXT, created_at TEXT, status TEXT)")
    con.execute("CREATE TABLE recipes (id INTEGER PRIMARY KEY, status TEXT)")
    con.executemany("INSERT INTO strategies (id, name, wfo_result, created_at, status) "
                    "VALUES (?,?,?,?,?)", [
        (724, "RCP-CLUSTER: fx1_4h_trend_pullback", '{"tier":"B"}',
         space_ts(NOW_DT - timedelta(days=2)), "validated"),
        (317, "RCP-CLUSTER: metal_reversion", '{"tier":"A"}',
         space_ts(NOW_DT - timedelta(days=3)), "validated"),
        (300, "RCP-CLUSTER: old", '{"tier":"C"}',
         space_ts(NOW_DT - timedelta(days=40)), "archived"),
    ])
    con.executemany("INSERT INTO recipes (status) VALUES (?)",
                    [("done",), ("done",), ("queued",), ("running",)])
    con.commit()
    con.close()

    # ── site-root ──
    _w(os.path.join(root, "api", "data", "pipeline_status.json"),
       {"summary": {"total_assets": 10, "ok": 8, "warn": 2, "stale": 0,
                    "generated_at": space_ts(NOW_DT)}})

    for p in (os.path.join(fx, "data", "bot1_balance.json"),
              os.path.join(fx, "data", "bot1_balance_history.json"),
              os.path.join(fx, "data", "bot1_risk_state.json"),
              os.path.join(fx, "data", "bot1_trades.jsonl"),
              os.path.join(fx, "data", "bot4_balance.json"),
              os.path.join(fx, "data", "bot4_trades.jsonl"),
              os.path.join(fx, "data", "shadow", "shadow_trades.jsonl"),
              os.path.join(fx, "data", "rotation", "rotation_state.json"),
              os.path.join(fx, "config", "deploy_registry.json"),
              os.path.join(fx, "config", "risk_guards.json"),
              os.path.join(fx, "config", "rotation_policy.json"),
              os.path.join(sl, "data", "worker_status.json"),
              os.path.join(root, "api", "data", "pipeline_status.json")):
        if os.path.exists(p):
            _touch(p, 60.0)

    return {"root": root, "fx": fx, "sl": sl, "td": td}


# ══════════════════════════════════════════════════════════════════════════════
# decay/tca-Fakes (monkeypatch; schreiben die Output-Datei wie der echte Lauf)
# ══════════════════════════════════════════════════════════════════════════════

CALLS = {"decay": 0, "tca": 0}


def fake_decay(rows):
    def _run(fx_root, out_path, now_epoch=None):
        CALLS["decay"] += 1
        doc = {"schema": "decay_monitor_v1", "summary": {"total": len(rows)},
               "bots": rows}
        os.makedirs(os.path.dirname(str(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return doc
    return _run


def fake_tca(p90):
    def _run(fx_root, out_path, now_epoch=None):
        CALLS["tca"] += 1
        doc = {"schema": "tca_report_v1",
               "groups": {"overall": {"n": 9, "mean_bps": 0.5, "p90_bps": p90}}}
        os.makedirs(os.path.dirname(str(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return doc
    return _run


def run_build(base, decay_rows=None, tca_p90=1.2, **fixture_kw):
    fx_kw = make_fixture(base, **fixture_kw)
    m.run_decay_monitor = fake_decay(decay_rows if decay_rows is not None
                                     else [{"bot": "bot1", "sid": 724,
                                            "status": "ok", "reasons": []}])
    m.run_tca_report = fake_tca(tca_p90)
    return m.build(fx_kw["root"], fx_kw["fx"], fx_kw["sl"], fx_kw["td"], now=NOW)


# ══════════════════════════════════════════════════════════════════════════════
# Tests (18 asserts)
# ══════════════════════════════════════════════════════════════════════════════

def main():
    base = tempfile.mkdtemp(prefix="ovtest_", dir=HERE)
    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            print(f"FAIL  {name}: unexpected {exc.__class__.__name__}: {exc}")

    def t_schema():
        doc = DOCS["base"]
        assert doc["schema"] == "overview_v1" and set(doc.keys()) == {
            "schema", "generated_at_utc", "generated_at_bz", "market_open",
            "verdict", "findings", "live", "shadow", "lab", "charts", "sources",
        }, f"schema/top-keys falsch: {doc.get('schema')} / {sorted(doc.keys())}"

    def t_fleet():
        fleet = DOCS["base"]["live"]["fleet"]
        assert [b["bot"] for b in fleet] == ["bot1", "bot4"], \
            f"fleet falsch: {[b['bot'] for b in fleet]}"

    def t_equity():
        b1 = DOCS["base"]["live"]["fleet"][0]
        kpis = DOCS["base"]["live"]["kpis"]
        assert (b1["equity"], b1["balance"], kpis["equity_demo"],
                kpis["equity_live"]) == (985.1, 982.34, 985.1, None), \
            f"equity/balance falsch: {b1['equity']}/{b1['balance']} kpis={kpis['equity_demo']}/{kpis['equity_live']} (risk_state-EUR + money_digits-Skalierung; live-Bot ohne Equity → null statt 0)"

    def t_pnl_windows():
        b1 = DOCS["base"]["live"]["fleet"][0]
        b4 = DOCS["base"]["live"]["fleet"][1]
        pd = DOCS["base"]["charts"]["pnl_daily_30d"]
        assert (b1["pnl_7d"], b1["pnl_30d"], b4["pnl_7d"], len(pd)) == \
            (9.5, 29.5, 12.0, 4), \
            f"PnL-Fenster falsch: 7d={b1['pnl_7d']} 30d={b1['pnl_30d']} bot4={b4['pnl_7d']} daily={pd}"

    def t_is_live():
        b1 = DOCS["base"]["live"]["fleet"][0]
        b4 = DOCS["base"]["live"]["fleet"][1]
        assert (b1["is_live"], b4["is_live"], b4["dd_level"], b4["blocked"],
                b1["multi"], b4["open_positions"]) == \
            (False, True, None, False, True, 0), \
            f"is_live/dd/multi falsch: {b1['is_live']}/{b4['is_live']}/{b4['dd_level']}/{b4['blocked']}/{b1['multi']}/{b4['open_positions']}"

    def t_shadow_kpis():
        k = DOCS["base"]["shadow"]["kpis"]
        assert (k["n_trades_30d"], k["net_30d"], k["n_deployed"]) == (8, 18.0, 2), \
            f"shadow kpis falsch (Mirror-Row muss raus): {k}"

    def t_ranking():
        r0 = DOCS["base"]["shadow"]["ranking"][0]
        r1 = DOCS["base"]["shadow"]["ranking"][1]
        assert (r0["sid"], r0["name"], r0["n"], r0["net"], r0["wr_pct"], r0["pf"],
                r0["tier"]) == \
            (724, "RCP-CLUSTER: fx1_4h_trend_pullback", 4, 12.0, 75.0, 4.0, "B") \
            and r1["sid"] == 317 and len(DOCS["base"]["shadow"]["ranking"]) == 2, \
            f"ranking falsch (30d-Fenster, Mirror raus): {r0} / {r1}"

    def t_challenges_rotation():
        ch = DOCS["base"]["shadow"]["challenges"]
        rot = {r["slot_id"]: r["state"] for r in DOCS["base"]["shadow"]["rotation"]}
        assert (ch[0]["sid"], ch[0]["days"], rot.get("s724"), rot.get("srot"),
                rot.get("s317")) == (999, 8, "held", "challenge", "held"), \
            f"challenge/rotation falsch: {ch} / {rot}"

    def t_curves():
        doc = DOCS["base"]
        b1 = doc["live"]["fleet"][0]
        tec = doc["live"]["total_equity_curve"]
        assert (len(b1["equity_curve"]), len(tec), tec[-1]) == (5, 5, tec[-1]) \
            and tec[-1][1] == 985.0 and len(tec) <= m.THRESH_CURVE_MAX_POINTS, \
            f"curves falsch: fleet={len(b1['equity_curve'])} total={tec[-1]}"

    def t_monthly():
        mp = DOCS["base"]["charts"]["monthly_pnl"]
        cur = mp[-1]
        prev = [e for e in mp if e["month"] == "2026-08"][0]
        assert len(mp) == 12 and (cur["month"], cur["demo_eur"], cur["live_eur"],
                                  cur["shadow_eur"]) == ("2026-09", 29.5, 12.0, 18.0) \
            and prev["demo_eur"] == 100.0 and prev["shadow_eur"] == 49.0, \
            f"monthly_pnl falsch: {cur} / 2026-08: {prev}"

    def t_exposure():
        exp = {e["class"]: e for e in DOCS["base"]["charts"]["exposure"]}
        assert (exp["FX"]["open_positions"], exp["METAL"]["open_positions"],
                exp["FX"]["slots"], exp["METAL"]["slots"],
                exp["FX"]["open_risk_eur"]) == (1, 1, 2, 1, None), \
            f"exposure falsch: {exp}"

    def t_corr():
        c = DOCS["base"]["charts"]["corr"]
        assert (c["labels"], c["matrix"][0][0], c["matrix"][0][1],
                c["matrix"][0][2]) == ([317, 724, 999], 1.0, 1.0, None), \
            f"corr falsch: labels={c['labels']} row0={c['matrix'][0]}"

    def t_sources():
        ids = [s["id"] for s in DOCS["base"]["sources"]]
        expected = {"fx.deploy_registry", "fx.risk_guards", "fx.rotation_policy",
                    "fx.rotation_state", "fx.shadow_trades", "td.spots_all",
                    "fx.balances", "fx.risk_states", "fx.trades",
                    "fx.balance_histories", "fx.positions", "sl.worker_status",
                    "sl.catalog_db", "site.pipeline_status", "overview.decay",
                    "overview.tca"}
        statuses = {s["id"]: s["status"] for s in DOCS["base"]["sources"]}
        assert expected <= set(ids) and statuses["site.pipeline_status"] == "fresh" \
            and statuses["td.spots_all"] == "fresh" \
            and all(s["status"] in ("fresh", "stale", "old", "missing")
                    for s in DOCS["base"]["sources"]), \
            f"sources unvollständig/falsch: missing={expected - set(ids)} pipe={statuses['site.pipeline_status']}"

    def t_verdict_yellow():
        doc = DOCS["base"]   # bot4 ohne risk_state → forced yellow
        comp = doc["verdict"]["components"]
        titles = [f["title"] for f in doc["findings"]]
        assert doc["verdict"]["overall"]["status"] == "yellow" \
            and comp["risk"]["status"] == "yellow" \
            and any("risk_state fehlt" in t for t in titles), \
            f"yellow-Mapping falsch: overall={doc['verdict']['overall']['status']} risk={comp['risk']['status']} titles={titles}"

    def t_verdict_red():
        doc = RED_DOC
        comp = doc["verdict"]["components"]
        assert doc["verdict"]["overall"]["status"] == "red" \
            and comp["shadow"]["status"] == "red" \
            and CALLS["decay"] >= 2 and CALLS["tca"] >= 2, \
            f"red-Mapping falsch: overall={doc['verdict']['overall']['status']} shadow={comp['shadow']['status']} calls={CALLS}"

    def t_verdict_green():
        doc = GREEN_DOC
        assert doc["verdict"]["overall"]["status"] == "green" and \
            all(c["status"] == "green"
                for c in doc["verdict"]["components"].values()), \
            f"green-Mapping falsch: {doc['verdict']['overall']} {[ (k, v['status']) for k, v in doc['verdict']['components'].items() ]}"

    def t_feed_red():
        doc = FEED_DOC
        data = doc["verdict"]["components"]["data"]
        exp = "red" if m.market_open(NOW_DT) else "yellow"
        assert data["status"] == exp and doc["verdict"]["overall"]["status"] == exp, \
            f"feed-rule falsch: data={data['status']} (erwartet {exp}, market_open={doc['market_open']})"

    def t_missing_root():
        ghost = os.path.join(base, "garnicht-da")
        doc = m.build(ghost, ghost, ghost, ghost, now=NOW)
        fleet = doc["live"]["fleet"]
        st = {s["id"]: s["status"] for s in doc["sources"]}
        assert fleet == [] and doc["verdict"]["overall"]["status"] == "yellow" \
            and st["fx.shadow_trades"] == "missing" \
            and st["sl.catalog_db"] == "missing", \
            f"missing-root falsch: fleet={fleet} overall={doc['verdict']['overall']['status']}"

    # Ausführung
    DOCS = {}
    DOCS["base"] = run_build(base)                                   # bot4 leer → yellow
    RED_DOC = run_build(os.path.join(base, "v_red"),
                        decay_rows=[{"bot": "bot3", "sid": 372,
                                     "status": "demote", "reasons": ["pf28 0.83<0.9"]}])
    GREEN_DOC = run_build(os.path.join(base, "v_green"), with_empty_bot=False)
    FEED_DOC = run_build(os.path.join(base, "v_feed"), with_empty_bot=False,
                         feed_age_s=1200.0)

    for name, fn in [
        ("schema+top-keys", t_schema),
        ("fleet-discovery", t_fleet),
        ("equity/balance-Skalierung", t_equity),
        ("PnL-Fenster 7/30d + daily", t_pnl_windows),
        ("is_live/dd_level/blocked/multi", t_is_live),
        ("shadow-kpis+mirror-exclusion", t_shadow_kpis),
        ("ranking aus catalog", t_ranking),
        ("challenge+rotation", t_challenges_rotation),
        ("curves+total_curve", t_curves),
        ("monthly_pnl 12 Monate", t_monthly),
        ("exposure-Klassen", t_exposure),
        ("corr-Matrix", t_corr),
        ("sources vollständigkeit", t_sources),
        ("verdict YELLOW (risk_state fehlt)", t_verdict_yellow),
        ("verdict RED (decay demote)", t_verdict_red),
        ("verdict GREEN (healthy)", t_verdict_green),
        ("feed-rule red@market_open", t_feed_red),
        ("missing-root: kein Crash", t_missing_root),
    ]:
        check(name, fn)

    shutil.rmtree(base, ignore_errors=True)
    print(f"\n{18 - len(failures)}/18 PASS, {len(failures)} FAIL")
    if failures:
        print("FAILS:", failures)
        sys.exit(1)
    print("ALLE PASS")


if __name__ == "__main__":
    main()