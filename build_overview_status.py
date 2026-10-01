#!/usr/bin/env python3
"""
build_overview_status.py — System-Overview Datenlayer (Schema overview_v1).

Aggregiert vorhandene Quellen (fx-bot-Daten, Strategy-Lab, Trading-Feed,
Site-Pipeline, decay/tca-Reports) zu api/overview/overview.json — die Daten-
grundlage für die neue Startseite des Kommandocenters.

NUR Datenlayer: keine HTML/CSS/JS-Arbeit, kein build.py/smart_rebuild-Lauf.

Quellen (alle read-only, defensiv — fehlt/kaputt → null-Felder + Finding,
NIE Crash):
  {fx}/data/bot{N}_balance.json           Balance/Equity je Bot (RAW-Einheiten
                                          + money_digits! fetch_bot_balance.py)
  {fx}/data/bot{N}_balance_history.json   Snapshots (timestamp ISO, balance,
                                          equity, open_pnl, positions, margin)
  {fx}/data/bot{N}_risk_state.json        risk_guard-State (equity, dd_pct,
                                          level, block, daily.pnl_pct, is_live)
  {fx}/data/bot{N}_positions_live.json    offene Positionen (Liste)
  {fx}/data/bot{N}_trades.jsonl           Trade-Log (closed_at, cTrader_profit
                                          Fallback pnl, strategy_id, symbol)
  {fx}/data/shadow/shadow_trades.jsonl    Shadow-Trades (int strategy_id,
                                          net_pnl, exit_ts)
  {fx}/data/rotation/rotation_state.json  Slots: {holder, challenge{...}}
  {fx}/config/rotation_policy.json        targets[].slot_ids/asset_class
  {fx}/config/deploy_registry.json        bots{} (strategy_id, demo, is_live)
  {fx}/config/risk_guards.json            Schwellen (.defaults — nie hardcoden)
  {td}/stream/spots_all.json              symbol → {bid,ask,spread,timestamp}
  {sl}/data/worker_status.json            Lab-Worker-Status
  {sl}/catalog.db                         recipes/strategies (READ-ONLY URI)
  {root}/api/data/pipeline_status.json    Data-Pipeline-Status (mtime-Alter)
  decay/tca: Subprozess sys.executable {fx}/scripts/decay_monitor.py --json
  bzw. scripts/tca_report.py --json (cwd={fx}, Timeout THRESH_SUBPROC_TIMEOUT_S)

Verhalten:
  - Atomarer Write (tmp + os.replace, Muster smart_rebuild.py:203-208).
  - Alle Schwellen als benannte THRESH_*-Konstanten (justierbar).
  - Keine Schein-Scores: nicht berechenbare Werte bleiben null.

CLI:
    python3 build_overview_status.py [--root DIR] [--fx-root DIR]
        [--sl-root DIR] [--trading-data DIR] [--out FILE] [--now EPOCH]

Output: <root>/api/overview/overview.json (schema "overview_v1")
"""

import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "overview_v1"

# ── Schwellen (justierbar) ────────────────────────────────────────────────────
THRESH_FEED_RED_S = 900        # Spot-Feed-Alter → red (bei market_open), sonst yellow
THRESH_FEED_YELLOW_S = 300     # Spot-Feed-Alter → yellow
THRESH_BALANCE_RED_S = 7200    # botN_balance.json mtime-Alter > 2h → red
THRESH_BALANCE_YELLOW_S = 1800 # > 30 min → yellow
THRESH_WORKER_STALE_S = 1800   # worker_status.json > 30 min alt → yellow
THRESH_SRC_FRESH_S = 1800      # generische Quellen: age <= → "fresh"
THRESH_SRC_OLD_S = 86400       # age <= → "old", sonst "stale"
THRESH_TCA_P90_BPS = 2.0       # TCA p90-Slippage (bps) darüber → yellow
THRESH_CHALLENGE_INFO_DAYS = 7 # Challenge-Tag >= → info-Finding
THRESH_RISK_RED_LEVEL = 2      # risk_state.level >= → red (L2-Block-Ladder)
THRESH_RISK_YELLOW_LEVEL = 1   # level == 1 → yellow
THRESH_SUBPROC_TIMEOUT_S = 90  # Timeout decay/tca-Subprozess
THRESH_CURVE_MAX_POINTS = 1500  # equity_curve / total_equity_curve ≤ 1500 Punkte
                                # (2026-10-01: 400→1500 — 400 straffte 15 Tage auf ~80-min-
                                #  Raster und ließ die Zeitachse grob wirken; 1500 ≈ volle
                                #  15-min-Quellauflösung der balance_history, ~14k Punkte
                                #  Gesamt-JSON bleibt für Browser/Chart unkritisch.)
CURVE_GRID_MIN_S = 900          # feinstes gemeinsames Zeitraster der Equity-Kurven
                                # (15 min) — siehe _align_grid/_grid_bucket_s
THRESH_CORR_MAX_SIDS = 8       # corr.labels ≤ 8 SIDs
THRESH_RANKING_TOP = 15        # shadow ranking Top 15
THRESH_MONTHS = 12             # monthly_pnl Fenster
THRESH_PNL_WINDOW_DAYS = (7, 30)

# ── Symbol-Klassen (Konstanten, kommentiert) ─────────────────────────────────
# METAL-Präfixe (contract_sizes.py-Konvention: XAU/XAG/XPT/XPD)
METAL_PREFIXES = ("XAU", "XAG", "XPT", "XPD")
# Index-Set = exakt contract_sizes.py:_INDICES (fx-bot/src/contract_sizes.py:132-134)
INDEX_SYMBOLS = {
    "US30", "US500", "NAS100", "US2000", "DE40", "UK100", "AUS200", "FRA40",
    "JP225", "HK50", "CN50", "GER40", "JPN225", "EUSTX50", "SPA35",
}
# Lab-Worker-Statuswerte, die als "läuft" gelten (vom Worker geschrieben;
# beobachtete Werte: recipe_running/designing/idle — siehe
# site/src/content/strategy-lab.html:1436-1442)
# Audit-Fix 01.10.2026: Der Worker (run_continuous._update_worker_status) schreibt
# 10 Statuswerte; die alte 3er-Whitelist erzeugte Fehlalarme ("Lab-Worker läuft nicht"),
# sobald der Worker z.B. in 'prescreen'/'saving'/'testing'/'idle' stand.
# Stale-Erkennung bleibt über das Datei-Alter (THRESH_WORKER_STALE_S) erhalten.
WORKER_RUNNING_STATES = {"recipe_running", "designing", "running", "genome_running",
                         "idle", "idle_seeding", "improving", "paused", "prescreen",
                         "saving", "testing"}

EXPOSURE_CLASSES = ("FX", "METAL", "INDEX")
SEV_ORDER = {"info": 0, "yellow": 1, "red": 2}
COMPONENTS = ("lab", "shadow", "demo_live", "risk", "data")

BERLIN_TZ = ZoneInfo("Europe/Berlin")


# ══ Basis-Helfer ══════════════════════════════════════════════════════════════

def _f(value):
    """Toleranter float-Cast; None wenn unmöglich; bool explizit ausgeschlossen."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            v = float(value)
            return v if math.isfinite(v) else None
        except ValueError:
            return None
    return None


def _i(value):
    """Toleranter int-Cast; None wenn unmöglich."""
    fv = _f(value)
    return int(fv) if fv is not None else None


def _parse_dt(value):
    """ISO- oder 'YYYY-MM-DD HH:MM:SS'-Timestamp → aware UTC datetime; sonst None.

    Toleriert 'Z'-Suffix und naive Strings (→ UTC angenommen)."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip().replace("Z", "+00:00")
    if "T" not in s and len(s) >= 19:
        s = s[:19].replace(" ", "T", 1) + s[19:]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _epoch(value):
    """Timestamp-String/Epoch → epoch-Sekunden (float) oder None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    dt = _parse_dt(value)
    return dt.timestamp() if dt else None


def _mtime_age_s(path, now_dt):
    """Datei-Alter in Sekunden (mtime) oder None (fehlend)."""
    try:
        return max(0.0, now_dt.timestamp() - os.path.getmtime(path))
    except OSError:
        return None


def _read_json(path):
    """JSON-Datei tolerant lesen; (data, err). err=None bei Erfolg."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "missing"
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as exc:
        return None, f"unreadable ({exc.__class__.__name__})"


def _round2(x):
    return None if x is None else round(x + 0.0, 2)


def _downsample(points, max_points=THRESH_CURVE_MAX_POINTS):
    """[(ts, val)] auf ≤ max_points straffen; erster + letzter Punkt bleiben."""
    if len(points) <= max_points:
        return list(points)
    stride = -(-len(points) // max_points)
    kept = points[::stride]
    if kept and kept[-1][0] != points[-1][0]:
        kept.append(points[-1])
    return kept


def _grid_bucket_s(curves, target=THRESH_CURVE_MAX_POINTS, min_s=CURVE_GRID_MIN_S):
    """Gemeinsames Zeitraster (Sekunden) über ALLE Kurven: span/target, auf 5 min
    aufgerundet, mindestens min_s. Grund (User-Feedback 01.10.2026): Die Chart-
    Zeitachse ist die UNION der Zeitstempel aller Serien (~11× so viele Zeiten wie
    Punkte je Serie) — dann kann selbst fitContent() bei minimalem barSpacing
    (0.5 px) nicht die volle Spanne zeigen und die Achse startet faktisch bei
    „vor ein paar Stunden“. Mit Raster: eine gemeinsame Zeitbasis, volle Range."""
    ts_all = [p[0] for c in curves for p in (c or [])]
    if len(ts_all) < 2:
        return min_s
    step = max(min_s, (max(ts_all) - min(ts_all)) / float(target))
    return int(-(-step // 300.0) * 300)


def _align_grid(points, bucket_s):
    """[(ts, val)] auf das gemeinsame Zeitraster legen — je Bucket der LETZTE Wert
    (Punkte sind zeitlich sortiert). Alle Serien erhalten identische Zeitstempel."""
    if not points or not bucket_s or bucket_s <= 0:
        return list(points)
    out = []
    for ts, v in points:
        b = int(ts // bucket_s) * bucket_s
        if out and out[-1][0] == b:
            out[-1][1] = v
        else:
            out.append([b, v])
    return out


def _pearson(xs, ys):
    """Pearson-Korrelation; None bei n<2 oder Varianz 0 (keine Schein-Werte)."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return None
    return cov / math.sqrt(vx * vy)


def symbol_class(symbol):
    """Symbol → 'FX'|'METAL'|'INDEX'|None (unbekannt → None, keine Annahme)."""
    s = str(symbol or "").upper().strip()
    if not s:
        return None
    if s.startswith(METAL_PREFIXES):
        return "METAL"
    if s in INDEX_SYMBOLS:
        return "INDEX"
    if len(s) == 6 and s.isalpha():
        return "FX"
    return None


def market_open(now_dt):
    """Vereinfachte FX-Markt-Regel (UTC): geschlossen Sa ganztags, So < 21:00,
    Fr >= 21:00; sonst offen."""
    wd = now_dt.weekday()  # 0=Mo … 6=So
    hour = now_dt.hour
    if wd == 5:                     # Samstag
        return False
    if wd == 6 and hour < 21:       # Sonntag vor 21:00 UTC
        return False
    if wd == 4 and hour >= 21:      # Freitag ab 21:00 UTC
        return False
    return True


# ══ Subprozess-Wrapper (Tests monkeypatchen DIESE beiden Funktionen) ═════════

def run_decay_monitor(fx_root, out_path, now_epoch=None):
    """decay_monitor.py als Subprozess ausführen; Report-Dict oder None.

    Aufruf exakt: sys.executable {fx}/scripts/decay_monitor.py --json <out>
    [--now ISO] (cwd={fx}, Timeout THRESH_SUBPROC_TIMEOUT_S). Fehler (Exit!=0,
    Timeout, fehlende/kaputte Output-Datei) → None."""
    # Absolute Pfade: der Subprozess wechselt cwd={fx_root} — relative Skript-/
    # Output-Pfade würden sonst relativ zum Kind-Cwd aufgelöst (Dry-Run-Fehler).
    fx_root = os.path.abspath(str(fx_root))
    out_path = os.path.abspath(str(out_path))
    script = os.path.join(fx_root, "scripts", "decay_monitor.py")
    if not os.path.exists(script):
        return None
    cmd = [sys.executable, script, "--json", str(out_path)]
    if now_epoch is not None:
        cmd += ["--now", datetime.fromtimestamp(now_epoch, tz=timezone.utc)
                .isoformat()]
    try:
        proc = subprocess.run(cmd, cwd=str(fx_root), timeout=THRESH_SUBPROC_TIMEOUT_S,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not os.path.exists(out_path):
        return None
    data, err = _read_json(out_path)
    return data if err is None else None


def run_tca_report(fx_root, out_path, now_epoch=None):
    """tca_report.py als Subprozess ausführen; Report-Dict oder None.

    Aufruf exakt: sys.executable {fx}/scripts/tca_report.py --json <out>
    (cwd={fx}, Timeout THRESH_SUBPROC_TIMEOUT_S)."""
    fx_root = os.path.abspath(str(fx_root))
    out_path = os.path.abspath(str(out_path))
    script = os.path.join(fx_root, "scripts", "tca_report.py")
    if not os.path.exists(script):
        return None
    cmd = [sys.executable, script, "--json", str(out_path)]
    try:
        proc = subprocess.run(cmd, cwd=str(fx_root), timeout=THRESH_SUBPROC_TIMEOUT_S,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not os.path.exists(out_path):
        return None
    data, err = _read_json(out_path)
    return data if err is None else None


# ══ Sources-Registry ══════════════════════════════════════════════════════════

class _Sources:
    """Sammelt sources[]-Einträge mit generischem Status-Mapping.

    Status: missing (fehlend/unlesbar) | fresh (<= fresh_s) | old (<= old_s)
    | stale (alt oder kaputt). fresh_s/old_s je Quelle überschreibbar (Feed-
    und Balance-Regeln haben eigene Schwellen)."""

    def __init__(self, now_dt):
        self.now_dt = now_dt
        self.items = []

    def add(self, sid, path, age_s, note, fresh_s=THRESH_SRC_FRESH_S,
            old_s=THRESH_SRC_OLD_S, broken=False):
        if age_s is None:
            status = "stale" if broken else "missing"
            age_s = None
        elif age_s <= fresh_s:
            status = "fresh"
        elif age_s <= old_s:
            status = "old"
        else:
            status = "stale"
        self.items.append({
            "id": sid,
            "path": str(path),
            "age_s": _i(age_s),
            "status": status,
            "note": note or "",
        })
        return status


# ══ Findings ══════════════════════════════════════════════════════════════════

class _Findings:
    def __init__(self):
        self.items = []

    def add(self, severity, component, title, detail, link=None):
        self.items.append({
            "severity": severity,
            "component": component,
            "title": title,
            "detail": detail,
            "link": link,
        })

    def sorted(self):
        return sorted(self.items,
                      key=lambda x: (-SEV_ORDER.get(x["severity"], 0),
                                     x["component"], x["title"]))


# ══ Bot-Fleet ═════════════════════════════════════════════════════════════════

def _discover_bots(fx_root):
    """Vorhandene Bots unter bot1..bot10 erkennen (mindestens eine der
    bekannten Datendateien existiert)."""
    bots = []
    data_dir = os.path.join(fx_root, "data")
    for n in range(1, 11):
        bot = f"bot{n}"
        if any(os.path.exists(os.path.join(data_dir, f"{bot}{s}"))
               for s in ("_balance.json", "_balance_history.json",
                         "_risk_state.json", "_trades.jsonl",
                         "_positions_live.json")):
            bots.append(bot)
    return bots


def _load_balance_file(path):
    """botN_balance.json → (balance_eur, equity_eur, age_s|None, err).

    WICHTIG: fetch_bot_balance.py schreibt balance/equity in RAW-Einheiten
    (Quotierung ×10**money_digits) — Umrechnung /10**money_digits
    (fetch_bot_balance.py:199-203, shadow_portfolio_builder.py:253-257)."""
    data, err = _read_json(path)
    if data is None or not isinstance(data, dict):
        return None, None, None, err or "invalid"
    digits = _i(data.get("money_digits"))
    if digits is None or digits < 0:
        digits = 2
    scale = 10 ** digits if digits else 1
    bal = _f(data.get("balance"))
    eq = _f(data.get("equity"))
    return (bal / scale if bal is not None else None,
            eq / scale if eq is not None else None,
            None, err)


def _load_curve(path, now_dt):
    """botN_balance_history.json → (curve[(epoch, equity_eur)], last_balance,
    age_s, err). Equity bevorzugt (Sanity-Guard |equity−balance| ≤ max(75€,
    10%|balance|) gegen Alt-Artefakte — Regel shadow_portfolio_builder.py:293-298);
    Fallback balance. Snapshots sind EUR (risk_guard rechnet dd_pct direkt
    daraus, scripts/risk_guard.py:125-145)."""
    data, err = _read_json(path)
    age_s = _mtime_age_s(path, now_dt)
    if data is None or not isinstance(data, dict):
        return [], None, age_s, err or "invalid"
    snaps = data.get("snapshots")
    if not isinstance(snaps, list):
        return [], None, age_s, "no_snapshots"
    points = []
    last_balance = None
    for sn in snaps:
        if not isinstance(sn, dict):
            continue
        ts = _epoch(sn.get("timestamp"))
        bal = _f(sn.get("balance"))
        eq = _f(sn.get("equity"))
        if bal is not None:
            last_balance = bal
        v = bal
        if eq is not None and bal is not None and abs(eq - bal) <= max(75.0, 0.10 * abs(bal)):
            v = eq  # Equity (inkl. Floating-PnL) bevorzugt
        elif eq is not None and bal is None:
            v = eq
        if ts is None or v is None:
            continue
        points.append((ts, v))
    points.sort(key=lambda x: x[0])
    return points, last_balance, age_s, err


def _sum_trades(path, now_dt):
    """botN_trades.jsonl streamen → (sums{7,30}, daily{date:pnl}, monthly{ym:pnl}).

    PnL-Regel: cTrader_profit, Fallback pnl; nur Trades mit parsablem
    closed_at (ISO oder 'YYYY-MM-DD HH:MM:SS'). Fenster: 0 <= now-ep <= d*86400."""
    sums = {d: 0.0 for d in THRESH_PNL_WINDOW_DAYS}
    daily = {}
    monthly = {}
    min_daily = (now_dt - timedelta(days=THRESH_PNL_WINDOW_DAYS[-1])).date()
    months = _last_months(now_dt, THRESH_MONTHS)
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                dt = _parse_dt(rec.get("closed_at"))
                if dt is None:
                    continue
                pnl = _f(rec.get("cTrader_profit"))
                if pnl is None:
                    pnl = _f(rec.get("pnl"))
                if pnl is None:
                    continue
                ep = dt.timestamp()
                age = now_dt.timestamp() - ep
                for d in THRESH_PNL_WINDOW_DAYS:
                    if 0.0 <= age <= d * 86400:
                        sums[d] += pnl
                day = dt.date()
                if day >= min_daily:
                    daily[day.isoformat()] = daily.get(day.isoformat(), 0.0) + pnl
                ym = f"{dt.year:04d}-{dt.month:02d}"
                if ym in months:
                    monthly[ym] = monthly.get(ym, 0.0) + pnl
    except FileNotFoundError:
        return None, {}, {}
    except OSError:
        return None, {}, {}
    return sums, daily, monthly


def _load_positions(path):
    """botN_positions_live.json → (Liste der Positionen, age_s|None)."""
    data, _err = _read_json(path)
    if data is None:
        return [], None
    if isinstance(data, dict):
        pos = data.get("positions", data)
    else:
        pos = data
    if not isinstance(pos, list):
        return [], None
    return [p for p in pos if isinstance(p, dict)], None


def _bot_slots(bot, fx_root, policy, rot_state):
    """Slots je Bot: Multi-TOML-[[slots]] (id, strategy_id) + Rotationsslots
    aus policy targets[bot].slot_ids minus TOML-IDs (Holder/Challenge aus
    rotation_state.json slots.<id> — Konvention shadow_portfolio_builder.py:64-134).

    Rückgabe: [{"slot_id","sid","holder":bool,"challenge_start":epoch|null}], multi:bool"""
    slots = []
    toml_ids = set()
    try:
        import tomllib
        with open(os.path.join(fx_root, "config", f"{bot}_multi.toml"), "rb") as fh:
            doc = tomllib.load(fh)
        for s in doc.get("slots") or []:
            if isinstance(s, dict) and s.get("id") and s.get("strategy_id") is not None:
                toml_ids.add(str(s["id"]))
                slots.append({
                    "slot_id": str(s["id"]),
                    "sid": _i(s.get("strategy_id")),
                    "holder": True,          # Strategie-Slot = deployed
                    "challenge_start": None,
                })
    except (OSError, ValueError, ImportError):
        pass

    slots_state = rot_state.get("slots") if isinstance(rot_state, dict) else {}
    if not isinstance(slots_state, dict):
        slots_state = {}
    for t in (policy.get("targets") or []) if isinstance(policy, dict) else []:
        if not isinstance(t, dict) or t.get("bot") != bot:
            continue
        for rid in t.get("slot_ids") or []:
            rid = str(rid)
            if rid in toml_ids:
                continue  # Strategie-Slot aus der Multi-TOML → schon gemappt
            st = slots_state.get(rid) or {}
            if not isinstance(st, dict):
                st = {}
            ch = st.get("challenge") if isinstance(st.get("challenge"), dict) else {}
            ch_start = _epoch(ch.get("started")) if ch else None
            holder_val = st.get("holder")
            if holder_val is not None:
                sid = _i(holder_val)
                slots.append({"slot_id": rid, "sid": sid, "holder": True,
                              "challenge_start": None})
            elif ch and ch.get("candidate") is not None:
                slots.append({"slot_id": rid, "sid": _i(ch.get("candidate")),
                              "holder": False, "challenge_start": ch_start})
            else:
                slots.append({"slot_id": rid, "sid": None, "holder": False,
                              "challenge_start": None})
    multi = len(slots) > 1
    return slots, multi


# ══ Shadow ════════════════════════════════════════════════════════════════════

def _shadow_rows(path):
    """shadow_trades.jsonl zeilenweise lesen (tolerant) → Liste von Dicts."""
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        pass
    return rows


def _shadow_sid(row):
    """int strategy_id oder None ('<sid>@<bot>'-Mirror-Rows werden wie in
    decay_monitor.py:520-533 ausgeschlossen → keine Doppelzählung)."""
    sid = row.get("strategy_id")
    if isinstance(sid, bool):
        return None
    if isinstance(sid, int):
        return sid
    if isinstance(sid, str):
        if "@" in sid:
            return None
        try:
            return int(sid)
        except ValueError:
            return None
    return None


def _shadow_pnl(row):
    """net_pnl → pnl_eur → pnl (Konvention build_trend_status.py:_challenge_stats)."""
    for f in ("net_pnl", "pnl_eur", "pnl"):
        v = _f(row.get(f))
        if v is not None:
            return v
    return None


def _shadow_exit_epoch(row):
    """exit_ts (Epoch, Primär) → timestamp/entry_ts (ISO, Fallback)."""
    ep = _epoch(row.get("exit_ts"))
    if ep is not None:
        return ep
    for f in ("timestamp", "entry_ts"):
        ep = _epoch(row.get(f))
        if ep is not None:
            return ep
    return None


def _shadow_stats(rows, now_dt):
    """Aggregiert Shadow-Rows (nur int-sid, wie decay_monitor):
    kpis_30d {n, net}, ranking je sid ÜBER 30d {n, net, wr_pct, pf, last_ts}
    (Ranking-Fenster = 30d, aligniert mit kpis_30d — Design-Entscheidung),
    daily_30d je sid {sid: {date: pnl}}, monthly {ym: pnl}."""
    min_daily = (now_dt - timedelta(days=THRESH_PNL_WINDOW_DAYS[-1])).date()
    months = _last_months(now_dt, THRESH_MONTHS)
    now_ep = now_dt.timestamp()
    kpis = {"n": 0, "net": 0.0}
    per_sid = {}
    daily_by_sid = {}
    monthly = {}
    for r in rows:
        sid = _shadow_sid(r)
        if sid is None:
            continue
        pnl = _shadow_pnl(r)
        if pnl is None:
            continue
        ep = _shadow_exit_epoch(r)
        if ep is not None:
            age = now_ep - ep
            if 0.0 <= age <= THRESH_PNL_WINDOW_DAYS[-1] * 86400:
                kpis["n"] += 1
                kpis["net"] += pnl
                st = per_sid.setdefault(sid, {"n": 0, "net": 0.0, "wins": 0,
                                              "gross_win": 0.0, "gross_loss": 0.0,
                                              "last_ep": None})
                st["n"] += 1
                st["net"] += pnl
                if pnl > 0:
                    st["wins"] += 1
                    st["gross_win"] += pnl
                elif pnl < 0:
                    st["gross_loss"] += -pnl
                if st["last_ep"] is None or ep > st["last_ep"]:
                    st["last_ep"] = ep
                day = datetime.fromtimestamp(ep, tz=timezone.utc).date()
                if day >= min_daily:
                    daily_by_sid.setdefault(sid, {})
                    daily_by_sid[sid][day.isoformat()] = \
                        daily_by_sid[sid].get(day.isoformat(), 0.0) + pnl
            ym = datetime.fromtimestamp(ep, tz=timezone.utc).strftime("%Y-%m")
            if ym in months:
                monthly[ym] = monthly.get(ym, 0.0) + pnl
    return kpis, per_sid, daily_by_sid, monthly


def _last_months(now_dt, count=THRESH_MONTHS):
    """Die letzten `count` Kalendermonate (inkl. aktueller) als 'YYYY-MM'-Set,
    ältester zuerst."""
    out = []
    y, m = now_dt.year, now_dt.month
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return set(reversed(out))


def _month_list(now_dt, count=THRESH_MONTHS):
    """Wie _last_months, aber als sortierte Liste (chronologisch)."""
    return sorted(_last_months(now_dt, count))


# ══ Strategy-Lab ══════════════════════════════════════════════════════════════

def _catalog_stats(db_path, now_dt):
    """catalog.db READ-ONLY öffnen (URI mode=ro — Konvention
    build_trend_status.py:723). Queries exakt nach Auftrag:
    recipes-Queue, strategies 7d-Count, Tier-Gruppierung (7d-Fenster),
    plus name/tier-Map fürs Shadow-Ranking. Fehler → (None-Teile, err)."""
    empty = (None, None, {}, {})
    if not os.path.exists(db_path):
        return empty, "missing"
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return empty, f"open failed ({exc.__class__.__name__})"
    try:
        queue_counts = {}
        try:
            for status, cnt in con.execute(
                    "SELECT status, COUNT(*) FROM recipes GROUP BY status"):
                queue_counts[str(status)] = int(cnt)
        except sqlite3.Error:
            queue_counts = {}

        cutoff = (now_dt - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        total_7d = 0
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM strategies WHERE created_at >= ?",
                (cutoff,)).fetchone()
            total_7d = int(row[0]) if row else 0
        except sqlite3.Error:
            total_7d = 0

        by_tier = {}
        try:
            for tier, cnt in con.execute(
                    "SELECT COALESCE(json_extract(wfo_result,'$.tier'),'?'), COUNT(*) "
                    "FROM strategies WHERE created_at >= ? GROUP BY 1", (cutoff,)):
                by_tier[str(tier)] = int(cnt)
        except sqlite3.Error:
            by_tier = {}

        names, tiers = {}, {}
        try:
            for sid, name, tier in con.execute(
                    "SELECT id, name, COALESCE(json_extract(wfo_result,'$.tier'),'?') "
                    "FROM strategies"):
                names[int(sid)] = str(name) if name else None
                tiers[int(sid)] = str(tier) if tier is not None else None
        except (sqlite3.Error, TypeError, ValueError):
            pass
        return (queue_counts, total_7d, by_tier, {"names": names, "tiers": tiers}), None
    finally:
        con.close()


# ══ Build ═════════════════════════════════════════════════════════════════════

def build(root, fx_root, sl_root, trading_data, now=None):
    """Komplettes overview_v1-Dokument bauen. now: epoch (None → wall clock)."""
    now_epoch = float(now) if now is not None else time.time()
    now_dt = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    sources = _Sources(now_dt)
    findings = _Findings()
    claimed_sources = set()   # "je Quelle max 1 Finding" für Pflichtquellen

    def src_finding(sid, component, title, detail, link=None):
        """Yellow-Finding für fehlende/stale Pflichtquelle — max 1 je Quelle."""
        if sid in claimed_sources:
            return
        claimed_sources.add(sid)
        findings.add("yellow", component, title, detail, link)

    # ── Konfig-Quellen (fx) ───────────────────────────────────────────────
    registry, reg_err = _read_json(os.path.join(fx_root, "config", "deploy_registry.json"))
    reg_age = _mtime_age_s(os.path.join(fx_root, "config", "deploy_registry.json"), now_dt)
    sources.add("fx.deploy_registry", os.path.join(fx_root, "config", "deploy_registry.json"),
                reg_age, "Deploy-Registry (bots, shadow_mapping)" if registry else reg_err)
    if registry is None:
        src_finding("fx.deploy_registry", "demo_live", "Deploy-Registry fehlt/kaputt",
                    f"{reg_err or 'missing'} — Fleet-Metadaten unvollständig",
                    "api/fx/dashboard.json")

    guards, guard_err = _read_json(os.path.join(fx_root, "config", "risk_guards.json"))
    sources.add("fx.risk_guards", os.path.join(fx_root, "config", "risk_guards.json"),
                _mtime_age_s(os.path.join(fx_root, "config", "risk_guards.json"), now_dt),
                "Risk-Guard-Schwellen (.defaults)" if guards else guard_err)
    if guards is None:
        src_finding("fx.risk_guards", "risk", "risk_guards.json fehlt/kaputt",
                    f"{guard_err or 'missing'} — Schwellen nicht lesbar (keine Hardcodes)")
    guard_defaults = guards.get("defaults") if isinstance(guards, dict) else None
    guard_defaults = guard_defaults if isinstance(guard_defaults, dict) else {}
    guard_l1 = _f(guard_defaults.get("l1_alert_pct"))
    guard_l2 = _f(guard_defaults.get("l2_block_pct"))

    policy, pol_err = _read_json(os.path.join(fx_root, "config", "rotation_policy.json"))
    sources.add("fx.rotation_policy", os.path.join(fx_root, "config", "rotation_policy.json"),
                _mtime_age_s(os.path.join(fx_root, "config", "rotation_policy.json"), now_dt),
                "Rotation-Policy (targets, challenge_days)" if policy else pol_err)
    if policy is None:
        src_finding("fx.rotation_policy", "shadow", "rotation_policy.json fehlt/kaputt",
                    f"{pol_err or 'missing'} — Slots/Challenges unvollständig")

    rot_state, rot_err = _read_json(os.path.join(fx_root, "data", "rotation", "rotation_state.json"))
    sources.add("fx.rotation_state", os.path.join(fx_root, "data", "rotation", "rotation_state.json"),
                _mtime_age_s(os.path.join(fx_root, "data", "rotation", "rotation_state.json"), now_dt),
                "Rotation-State (holder, challenge)" if rot_state else rot_err)
    if rot_state is None:
        src_finding("fx.rotation_state", "shadow", "rotation_state.json fehlt/kaputt",
                    f"{rot_err or 'missing'} — Rotation-/Challenge-Daten null")

    shadow_path = os.path.join(fx_root, "data", "shadow", "shadow_trades.jsonl")
    shadow_rows = _shadow_rows(shadow_path)
    shadow_file_ok = os.path.exists(shadow_path)
    sources.add("fx.shadow_trades", shadow_path,
                _mtime_age_s(shadow_path, now_dt),
                f"{len(shadow_rows)} Shadow-Rows" if shadow_file_ok else "missing")
    if not shadow_file_ok:
        src_finding("fx.shadow_trades", "shadow", "shadow_trades.jsonl fehlt",
                    "Shadow-Ranking/KPIs null", "api/portfolio.json")

    # ── Spots / Feed ──────────────────────────────────────────────────────
    spots_path = os.path.join(trading_data, "stream", "spots_all.json")
    spots, spots_err = _read_json(spots_path)
    feed_age = None
    if isinstance(spots, dict) and spots:
        newest = None
        for v in spots.values():
            if isinstance(v, dict):
                ep = _epoch(v.get("timestamp"))
                if ep is not None and (newest is None or ep > newest):
                    newest = ep
        if newest is not None:
            feed_age = max(0.0, now_epoch - newest)
    spots_age = feed_age if feed_age is not None else _mtime_age_s(spots_path, now_dt)
    sources.add("td.spots_all", spots_path, spots_age,
                (f"Feed-Alter {int(feed_age)}s (neuester Spot-Timestamp)"
                 if feed_age is not None else (spots_err or "missing")))
    if spots is None:
        src_finding("td.spots_all", "data", "spots_all.json fehlt/kaputt",
                    f"{spots_err or 'missing'} — Feed-Alter/Freshness unbekannt")

    # ── Fleet (Bots) ──────────────────────────────────────────────────────
    bots = _discover_bots(fx_root)
    fleet = []
    bot_daily_total = {}       # date → pnl (Demo+Live)
    bot_monthly = {"demo": {}, "live": {}}
    pos_class_counts = {"FX": 0, "METAL": 0, "INDEX": 0}
    pos_open_total = 0
    bal_family_age = None      # max Alter über vorhandene balance-Dateien
    bal_family_missing = []
    rs_family_status = []      # pro Bot: risk_state vorhanden?
    rs_family_age = None
    trades_family_missing = []
    trades_family_age = None
    hist_family_age = None
    hist_present = 0
    pos_family_age = None
    curves_by_bot = {}

    # ── Gemeinsames Zeitraster ALLER Equity-Kurven (User-Feedback 01.10.2026) ──
    # Vorab-Load + einmaliges Rastern (Cache): alle Serien bekommen dieselben
    # Zeitstempel → Chart-Zeitachse zeigt via fitContent die VOLLE Spanne.
    hist_cache = {}
    for bot in bots:
        hist_cache[bot] = _load_curve(
            os.path.join(fx_root, "data", f"{bot}_balance_history.json"), now_dt)
    curve_bucket_s = _grid_bucket_s([t[0] for t in hist_cache.values()])
    for bot in bots:
        pts, lb, age, err = hist_cache[bot]
        hist_cache[bot] = (_align_grid(pts, curve_bucket_s), lb, age, err)

    for bot in bots:
        bdir = os.path.join(fx_root, "data")
        bal_path = os.path.join(bdir, f"{bot}_balance.json")
        hist_path = os.path.join(bdir, f"{bot}_balance_history.json")
        rs_path = os.path.join(bdir, f"{bot}_risk_state.json")
        trades_path = os.path.join(bdir, f"{bot}_trades.jsonl")
        pos_path = os.path.join(bdir, f"{bot}_positions_live.json")

        bal_eur, bal_eq_eur, _, bal_err = _load_balance_file(bal_path)
        bal_age = _mtime_age_s(bal_path, now_dt)
        if bal_age is not None:
            bal_family_age = bal_age if bal_family_age is None else max(bal_family_age, bal_age)
        else:
            bal_family_missing.append(bot)

        curve, hist_last_bal, hist_age, hist_err = hist_cache[bot]
        curves_by_bot[bot] = curve
        if hist_age is not None:
            hist_family_age = hist_age if hist_family_age is None \
                else max(hist_family_age, hist_age)
        if os.path.exists(hist_path):
            hist_present += 1

        rs, rs_err = _read_json(rs_path)
        rs_ok = rs is not None
        rs_family_status.append(rs_ok)
        if rs_ok:
            rs_age = _mtime_age_s(rs_path, now_dt)
            if rs_age is not None:
                rs_family_age = rs_age if rs_family_age is None else max(rs_family_age, rs_age)

        positions, _ = _load_positions(pos_path)
        pos_age = _mtime_age_s(pos_path, now_dt)
        if pos_age is not None:
            pos_family_age = pos_age if pos_family_age is None \
                else max(pos_family_age, pos_age)
        pos_open_total += len(positions)
        for p in positions:
            cls = symbol_class(p.get("symbol"))
            if cls:
                pos_class_counts[cls] += 1

        tr_age = _mtime_age_s(trades_path, now_dt)
        trades_sums, trades_daily, trades_monthly = _sum_trades(trades_path, now_dt)
        if trades_sums is None:
            trades_family_missing.append(bot)
            trades_sums = {d: None for d in THRESH_PNL_WINDOW_DAYS}  # null statt 0
        elif tr_age is not None:
            # min = FRISCHESTE Datei: idle Bots (bot4/8/9/10 handeln selten bzw.
            # tageweise gar nicht) sind normal und duerfen die Family nicht auf
            # "stale" ziehen — anders als balance/hist/rs/pos (Writer laufen minuetlich).
            trades_family_age = tr_age if trades_family_age is None \
                else min(trades_family_age, tr_age)

        reg_entry = {}
        if isinstance(registry, dict) and isinstance(registry.get("bots"), dict):
            reg_entry = registry["bots"].get(bot) or {}

        # is_live: risk_state.is_live falls vorhanden; sonst Registry:
        # demo=False → live; demo=True → demo; unknown → live (konservativ).
        is_live = None
        if rs_ok and isinstance(rs.get("is_live"), bool):
            is_live = rs["is_live"]
        else:
            demo = reg_entry.get("demo")
            is_live = False if demo is True else True

        sid_list_raw = reg_entry.get("strategy_id")
        sids = sid_list_raw if isinstance(sid_list_raw, list) else [sid_list_raw]

        slots, multi = _bot_slots(bot, fx_root, policy or {}, rot_state or {})
        if not multi and len([s for s in sids if _i(s) is not None]) > 1:
            multi = True  # Registry-Liste > 1 Strategie → multi

        equity = None
        if rs_ok:
            equity = _f(rs.get("equity"))
        if equity is None and curve:
            equity = curve[-1][1]
        if equity is None:
            equity = bal_eq_eur
        balance = bal_eur
        if balance is None:
            balance = hist_last_bal

        dd_pct = _f(rs.get("dd_pct")) if rs_ok else None
        dd_level = _i(rs.get("level")) if rs_ok else None
        if dd_level is None and dd_pct is not None:
            # Fallback OHNE Hardcode: Level aus risk_guards.defaults-Schwellen
            # ableiten (dd_pct ist <= 0, Schwellen positiv — risk_guard.py:257).
            ad = abs(dd_pct)
            if guard_l2 is not None and ad >= guard_l2:
                dd_level = 2
            elif guard_l1 is not None and ad >= guard_l1:
                dd_level = 1
        blocked = bool(rs.get("block")) if rs_ok else False
        daily_pnl_pct = None
        if rs_ok and isinstance(rs.get("daily"), dict):
            daily_pnl_pct = _f(rs["daily"].get("pnl_pct"))

        fleet.append({
            "bot": bot,
            "is_live": bool(is_live),
            "multi": bool(multi),
            "equity": _round2(equity),
            "balance": _round2(balance),
            "pnl_7d": _round2(trades_sums.get(7)),
            "pnl_30d": _round2(trades_sums.get(30)),
            "dd_pct": _round2(dd_pct),
            "dd_level": dd_level,
            "blocked": blocked,
            "daily_pnl_pct": _round2(daily_pnl_pct),
            "open_positions": len(positions),
            "slots": slots,
            "equity_curve": [[int(ts), _round2(v)] for ts, v in
                             _downsample(curve, THRESH_CURVE_MAX_POINTS)],
        })

        bucket = "live" if is_live else "demo"
        for ym, v in trades_monthly.items():
            bot_monthly[bucket][ym] = bot_monthly[bucket].get(ym, 0.0) + v
        for day, v in trades_daily.items():
            bot_daily_total[day] = bot_daily_total.get(day, 0.0) + v

        # Age-Findings je Bot (balance-source-Regel)
        if bal_age is not None:
            if bal_age > THRESH_BALANCE_RED_S:
                findings.add("red", "demo_live", f"{bot}: Balance-Quelle {int(bal_age/3600)}h alt",
                             f"{os.path.relpath(bal_path, fx_root)} mtime-Alter "
                             f"{int(bal_age)}s > {THRESH_BALANCE_RED_S}s")
            elif bal_age > THRESH_BALANCE_YELLOW_S:
                findings.add("yellow", "demo_live", f"{bot}: Balance-Quelle {int(bal_age/60)}min alt",
                             f"{os.path.relpath(bal_path, fx_root)} mtime-Alter "
                             f"{int(bal_age)}s > {THRESH_BALANCE_YELLOW_S}s")

        # Risk-Findings je Bot
        if rs_ok:
            level = dd_level if dd_level is not None else 0
            if blocked or (level is not None and level >= THRESH_RISK_RED_LEVEL):
                findings.add("red", "risk", f"{bot}: Risk-Level {level} / block={blocked}",
                             str(rs.get("block_reason") or
                                 f"dd_pct={_round2(dd_pct)}, level={level}"))
            elif level == THRESH_RISK_YELLOW_LEVEL:
                findings.add("yellow", "risk", f"{bot}: Risk-Level 1 (Alert)",
                             f"dd_pct={_round2(dd_pct)}")

    # Familien-Quellen-Einträge
    fam_bal_status = sources.add(
        "fx.balances", os.path.join(fx_root, "data", "bot*_balance.json"),
        bal_family_age,
        (f"{len(bots) - len(bal_family_missing)}/{len(bots)} Bots aktuell; "
         f"fehlen: {','.join(bal_family_missing) or '—'}") if bots else "keine Bots erkannt")
    if bots and fam_bal_status == "missing":
        src_finding("fx.balances", "demo_live", "Keine botN_balance.json vorhanden",
                    f"{len(bots)} Bots erkannt, aber keine Balance-Datei")

    rs_missing_bots = [b for b, ok in zip(bots, rs_family_status) if not ok]
    sources.add(
        "fx.risk_states", os.path.join(fx_root, "data", "bot*_risk_state.json"),
        rs_family_age,
        (f"{len(bots) - len(rs_missing_bots)}/{len(bots)} Bots mit risk_state; "
         f"fehlen: {','.join(rs_missing_bots) or '—'}") if bots else "keine Bots erkannt",
        broken=bool(rs_missing_bots))
    if bots and rs_missing_bots:
        src_finding("fx.risk_states", "risk",
                    "risk_state fehlt für " + ",".join(rs_missing_bots),
                    "dd_level/blocked → null/false (Konsens-Regel)")

    sources.add(
        "fx.trades", os.path.join(fx_root, "data", "bot*_trades.jsonl"),
        trades_family_age, (f"fehlen: {','.join(trades_family_missing) or '—'}")
        if bots else "keine Bots erkannt",
        broken=bool(trades_family_missing))
    if bots and len(trades_family_missing) == len(bots):
        src_finding("fx.trades", "demo_live", "Keine botN_trades.jsonl vorhanden",
                    "PnL-Fenster null")

    sources.add("fx.balance_histories",
                os.path.join(fx_root, "data", "bot*_balance_history.json"),
                hist_family_age, f"{hist_present}/{len(bots)} Bots mit Curve"
                if bots else "keine Bots erkannt")
    sources.add("fx.positions", os.path.join(fx_root, "data", "bot*_positions_live.json"),
                pos_family_age, f"{pos_open_total} offene Positionen gesamt")

    # ── Fleet-KPIs ────────────────────────────────────────────────────────
    def _kpi_sum(pred, field):
        """Summe über fleet-Werte; None wenn kein Bot einen Wert liefert
        (keine Schein-Nullen)."""
        vals = [b[field] for b in fleet if pred(b) and b[field] is not None]
        return _round2(sum(vals)) if vals else None

    equity_live = _kpi_sum(lambda b: b["is_live"], "equity")
    equity_demo = _kpi_sum(lambda b: not b["is_live"], "equity")
    kpi_7d = _kpi_sum(lambda b: True, "pnl_7d")
    kpi_30d = _kpi_sum(lambda b: True, "pnl_30d")
    total_equity = _kpi_sum(lambda b: True, "equity")

    # total_equity_curve: Union-TS, Forward-Fill, ≤1500 Punkte.
    # Basis: je-Bot-Curves (bereits auf ≤1500 Punkte gestrafft) — Union der
    # Timestamps, je Bot Forward-Fill (Werte erst ab erstem Bot-Punkt), Summe.
    curves_ds = {b: _downsample(curves_by_bot.get(b) or [],
                                THRESH_CURVE_MAX_POINTS) for b in bots}
    all_ts = sorted({ts for c in curves_ds.values() for ts, _v in c})
    union_curve = []
    idx_by_bot = {b: 0 for b in bots}
    last_by_bot = {b: None for b in bots}
    for ts in all_ts:
        total = 0.0
        any_val = False
        for bot in bots:
            pts = curves_ds[bot]
            i = idx_by_bot[bot]
            while i < len(pts) and pts[i][0] <= ts:
                last_by_bot[bot] = pts[i][1]
                i += 1
            idx_by_bot[bot] = i
            v = last_by_bot[bot]
            if v is not None:
                total += v
                any_val = True
        if any_val:
            union_curve.append((ts, total))
    total_curve_out = [[int(ts), _round2(v)] for ts, v in
                       _downsample(union_curve, THRESH_CURVE_MAX_POINTS)]

    live_kpis = {
        "equity_demo": equity_demo,
        "equity_live": equity_live,
        "equity_total": total_equity,
        "pnl_7d": kpi_7d,
        "pnl_30d": kpi_30d,
        "open_positions": pos_open_total,
    }

    # ── Shadow-KPIs / Ranking / Charts-Input ──────────────────────────────
    kpis_30d, per_sid, shadow_daily_by_sid, shadow_monthly = _shadow_stats(shadow_rows, now_dt)
    if not shadow_file_ok:
        # Fehlende/kaputte Shadow-Quelle → null-Felder (keine Schein-Nullen)
        kpis_30d = {"n": None, "net": None}
        shadow_daily_by_sid, shadow_monthly = {}, {}

    n_deployed = 0
    deployed_sids = set()
    if isinstance(registry, dict) and isinstance(registry.get("bots"), dict):
        for entry in registry["bots"].values():
            raw = entry.get("strategy_id") if isinstance(entry, dict) else None
            for s in (raw if isinstance(raw, list) else [raw]):
                sid = _i(s)
                if sid is not None:
                    deployed_sids.add(sid)
        n_deployed = len(deployed_sids)

    # ── Lab ───────────────────────────────────────────────────────────────
    worker_path = os.path.join(sl_root, "data", "worker_status.json")
    worker, worker_err = _read_json(worker_path)
    worker_age = _mtime_age_s(worker_path, now_dt)
    sources.add("sl.worker_status", worker_path, worker_age,
                f"status={worker.get('status')}" if worker else (worker_err or "missing"),
                fresh_s=THRESH_WORKER_STALE_S)
    if worker is None:
        src_finding("sl.worker_status", "lab", "worker_status.json fehlt/kaputt",
                    f"{worker_err or 'missing'} — Lab-Worker-Status unbekannt")

    catalog_path = os.path.join(sl_root, "catalog.db")
    (queue_counts, strat_7d_total, strat_7d_tiers, catalog_meta), cat_err = \
        _catalog_stats(catalog_path, now_dt)
    queue_counts = queue_counts or {}
    if strat_7d_total is None:
        strat_7d_total = 0
    strat_7d_tiers = strat_7d_tiers or {}
    cat_status = sources.add(
        "sl.catalog_db", catalog_path, _mtime_age_s(catalog_path, now_dt),
        cat_err or (f"queue={sum(queue_counts.values())} recipes, "
                    f"{strat_7d_total} Strategien 7d"))
    if cat_err is not None:
        src_finding("sl.catalog_db", "lab", "catalog.db fehlt/unlesbar",
                    cat_err, "api/strategy-lab/catalog.json")
    elif cat_status == "stale":
        src_finding("sl.catalog_db", "lab", "catalog.db stale",
                    f"mtime-Alter > {THRESH_SRC_OLD_S}s")

    worker_out = {
        "status": worker.get("status") if worker else None,
        "strategy_type": worker.get("strategy_type") if worker else None,
        "elapsed_s": _i(worker.get("elapsed_s")) if worker else None,
        "age_s": _i(worker_age),
        "message": worker.get("message") if worker else None,
    }
    lab_out = {
        "worker": worker_out,
        "queue_counts": queue_counts,
        "strategies_7d": {"total": strat_7d_total,
                          "by_tier": strat_7d_tiers},
    }

    # ── Pipeline-Status ───────────────────────────────────────────────────
    pipeline_path = os.path.join(root, "api", "data", "pipeline_status.json")
    pipeline, pipe_err = _read_json(pipeline_path)
    pipeline_age = _mtime_age_s(pipeline_path, now_dt)
    pipe_note = (pipe_err or ("generated_at="
                              + str((pipeline.get("summary") or {}).get("generated_at")))) \
        if pipeline else (pipe_err or "missing")
    pipe_status = sources.add("site.pipeline_status", pipeline_path, pipeline_age,
                              pipe_note)
    if pipeline is None or pipe_status == "stale":
        src_finding("site.pipeline_status", "data",
                    "pipeline_status.json fehlt/stale",
                    f"{pipe_err or 'missing'}" if pipeline is None
                    else f"mtime-Alter > {THRESH_SRC_OLD_S}s",
                    "api/data/pipeline_status.json")

    # ── decay / tca (Subprozess, in {root}/api/overview/) ─────────────────
    out_dir = os.path.join(root, "api", "overview")
    os.makedirs(out_dir, exist_ok=True)   # Zielverzeichnis anlegen (Spec)
    decay_path = os.path.join(out_dir, "decay_latest.json")
    tca_path = os.path.join(out_dir, "tca_latest.json")

    decay = run_decay_monitor(fx_root, decay_path, now_epoch=now_epoch)
    decay_age = _mtime_age_s(decay_path, now_dt)
    sources.add("overview.decay", decay_path, decay_age,
                "decay_monitor_v1" if decay else "Subprozess fehlgeschlagen / kein Output")
    if decay is None:
        src_finding("overview.decay", "shadow", "Decay-Report fehlt/stale",
                    f"decay_monitor.py exit!=0/timeout — {decay_path} unlesbar")

    tca = run_tca_report(fx_root, tca_path, now_epoch=now_epoch)
    tca_age = _mtime_age_s(tca_path, now_dt)
    sources.add("overview.tca", tca_path, tca_age,
                "tca_report_v1" if tca else "Subprozess fehlgeschlagen / kein Output")
    if tca is None:
        src_finding("overview.tca", "demo_live", "TCA-Report fehlt/stale",
                    f"tca_report.py exit!=0/timeout — {tca_path} unlesbar")

    # decay-Auswertung: Feldnamen aus ECHTEM Lauf (decay_monitor_v1):
    # bots[]{bot,sid,role,is_live,account_id,live,sim,ratio,status,status_label,reasons},
    # summary{total,tableau,demote,watch,ok,insufficient} — defensiv.
    decay_rows = decay.get("bots") if isinstance(decay, dict) else None
    if not isinstance(decay_rows, list):
        decay_rows = None
    decay_counts = decay.get("summary") if isinstance(decay, dict) else None
    if not isinstance(decay_counts, dict):
        decay_counts = None
    if decay_rows:
        for row in decay_rows:
            if not isinstance(row, dict):
                continue
            status = row.get("status")
            label = f"{row.get('bot')}/{row.get('sid')}"
            if status == "tableau":
                findings.add("red", "shadow", f"Decay TABLEAU: {label}",
                             "; ".join(map(str, row.get("reasons") or [])))
            elif status == "demote":
                findings.add("red", "shadow", f"Decay demote: {label}",
                             "; ".join(map(str, row.get("reasons") or [])))
            elif status == "watch":
                findings.add("yellow", "shadow", f"Decay watch: {label}",
                             "; ".join(map(str, row.get("reasons") or [])))

    # tca-Auswertung: groups.overall.p90_bps (Schema tca_report_v1 — Feldnamen aus
    # echtem Lauf der Workspace-Kopie verifiziert, 2026-09-29) — defensiv.
    tca_overall = {}
    if isinstance(tca, dict) and isinstance(tca.get("groups"), dict):
        tca_overall = tca["groups"].get("overall") or {}
    tca_p90 = _f(tca_overall.get("p90_bps")) if isinstance(tca_overall, dict) else None
    if tca_p90 is not None and tca_p90 > THRESH_TCA_P90_BPS:
        findings.add("yellow", "demo_live",
                     f"TCA p90-Slippage {tca_p90} bps > {THRESH_TCA_P90_BPS}",
                     f"overall.p90_bps (Threshold THRESH_TCA_P90_BPS={THRESH_TCA_P90_BPS})")

    # ── Challenges / Rotation (aus policy + state) ────────────────────────
    challenges = []
    rotation = []
    slots_state = rot_state.get("slots") if isinstance(rot_state, dict) else {}
    if not isinstance(slots_state, dict):
        slots_state = {}
    for t in (policy.get("targets") or []) if isinstance(policy, dict) else []:
        if not isinstance(t, dict):
            continue
        bot = t.get("bot")
        for rid in t.get("slot_ids") or []:
            rid = str(rid)
            st = slots_state.get(rid) or {}
            if not isinstance(st, dict):
                st = {}
            holder = st.get("holder")
            ch = st.get("challenge") if isinstance(st.get("challenge"), dict) else {}
            holder_sid = _i(holder)
            ch_sid = _i(ch.get("candidate")) if ch else None
            ch_start_ep = _epoch(ch.get("started")) if ch else None
            if holder_sid is not None:
                rotation.append({"bot": bot, "slot_id": rid, "sid": holder_sid,
                                 "holder": True, "state": "held"})
            elif ch_sid is not None:
                days = None
                start_dt = _parse_dt(ch.get("started"))
                if start_dt is not None:
                    days = max(1, (now_dt.date() - start_dt.date()).days + 1)
                rotation.append({"bot": bot, "slot_id": rid, "sid": ch_sid,
                                 "holder": False, "state": "challenge"})
                challenges.append({"bot": bot, "slot_id": rid, "sid": ch_sid,
                                   "start": ch.get("started"),
                                   "days": days})
                if days is not None and days >= THRESH_CHALLENGE_INFO_DAYS:
                    findings.add("info", "shadow",
                                 f"Challenge {bot}/{rid} läuft seit {days} Tagen",
                                 f"sid {ch_sid}, started {ch.get('started')}")
            else:
                rotation.append({"bot": bot, "slot_id": rid, "sid": None,
                                 "holder": False, "state": "open"})

    # ── Shadow-Ranking (Top 15) ───────────────────────────────────────────
    cat_names = catalog_meta.get("names", {}) if catalog_meta else {}
    cat_tiers = catalog_meta.get("tiers", {}) if catalog_meta else {}
    ranking = []
    for sid in sorted(per_sid, key=lambda s: (-per_sid[s]["net"], s)):
        st = per_sid[sid]
        n = st["n"]
        if n <= 0:
            continue
        pf = None
        if st["gross_loss"] > 0:
            pf = _round2(st["gross_win"] / st["gross_loss"])
        last_ts = None
        if st["last_ep"] is not None:
            last_ts = datetime.fromtimestamp(st["last_ep"], tz=timezone.utc) \
                .strftime("%Y-%m-%dT%H:%M:%SZ")
        ranking.append({
            "sid": sid,
            "name": cat_names.get(sid) or f"Strategy #{sid}",
            "n": n,
            "net": _round2(st["net"]),
            "wr_pct": round(st["wins"] / n * 100.0, 1),
            "pf": pf,
            "tier": cat_tiers.get(sid),
            "last_ts": last_ts,
        })
        if len(ranking) >= THRESH_RANKING_TOP:
            break

    # ── Charts ────────────────────────────────────────────────────────────
    months = _month_list(now_dt, THRESH_MONTHS)
    monthly_pnl = [{
        "month": ym,
        "demo_eur": _round2(bot_monthly["demo"].get(ym, 0.0)),
        "live_eur": _round2(bot_monthly["live"].get(ym, 0.0)),
        "shadow_eur": _round2(shadow_monthly.get(ym, 0.0)),
    } for ym in months]

    tca_groups = None
    if isinstance(tca, dict) and isinstance(tca.get("groups"), dict):
        tca_groups = tca["groups"]

    # corr: Pearson Tages-PnL (30d) der Slot-SIDs (≤8)
    slot_sids = sorted({s["sid"] for b in fleet for s in b["slots"]
                        if s["sid"] is not None})[:THRESH_CORR_MAX_SIDS]
    corr_dates = sorted({d for sid in slot_sids
                         for d in (shadow_daily_by_sid.get(sid) or {})})
    series = {}
    for sid in slot_sids:
        daily = shadow_daily_by_sid.get(sid) or {}
        series[sid] = [daily.get(d, 0.0) for d in corr_dates]
    matrix = []
    for a in slot_sids:
        row = []
        for b in slot_sids:
            r = _pearson(series[a], series[b])
            row.append(round(r, 3) if r is not None else None)
        matrix.append(row)

    # exposure: Klassen aus Positionen (resolvable symbols) + Slot-Zuordnung
    # über rotation_policy targets[bot].asset_class; open_risk_eur bewusst null
    # (bräuchte contract_sizes/EUR-Raten — keine Schein-Zahlen).
    bot_class = {}
    if isinstance(policy, dict):
        for t in policy.get("targets") or []:
            if isinstance(t, dict) and t.get("bot"):
                bot_class[t["bot"]] = t.get("asset_class")
    class_slots = {"FX": 0, "METAL": 0, "INDEX": 0}
    for b in fleet:
        cls = bot_class.get(b["bot"])
        if cls in class_slots:
            class_slots[cls] += len(b["slots"])
    exposure = [{
        "class": cls,
        "open_positions": pos_class_counts.get(cls, 0),
        "slots": class_slots.get(cls, 0),
        "open_risk_eur": None,
    } for cls in EXPOSURE_CLASSES]

    pnl_daily = sorted(bot_daily_total.items())
    pnl_daily_out = [[day, _round2(v)] for day, v in pnl_daily]

    # ── Worker-Findings ───────────────────────────────────────────────────
    w_status = worker_out["status"]
    w_age = worker_out["age_s"]
    if w_status is None or str(w_status).lower() not in WORKER_RUNNING_STATES \
            or (w_age is not None and w_age > THRESH_WORKER_STALE_S):
        findings.add("yellow", "lab", "Lab-Worker läuft nicht / Status stale",
                     f"status={w_status}, age_s={w_age}, "
                     f"erwartet ∈ {sorted(WORKER_RUNNING_STATES)}, "
                     f"age ≤ {THRESH_WORKER_STALE_S}s")

    # ── Feed-Findings ─────────────────────────────────────────────────────
    mkt_open = market_open(now_dt)
    if feed_age is not None:
        if feed_age > THRESH_FEED_RED_S:
            findings.add("red" if mkt_open else "yellow",
                         "data", f"Spot-Feed {int(feed_age/60)}min alt",
                         f"neuester Spot-Timestamp {int(feed_age)}s zurück "
                         f"(Threshold red={THRESH_FEED_RED_S}s, market_open={mkt_open})")
        elif feed_age > THRESH_FEED_YELLOW_S:
            findings.add("yellow", "data", f"Spot-Feed {int(feed_age/60)}min alt",
                         f"neuester Spot-Timestamp {int(feed_age)}s zurück "
                         f"(Threshold yellow={THRESH_FEED_YELLOW_S}s)")

    # ── Verdict ───────────────────────────────────────────────────────────
    components = {}
    for comp in COMPONENTS:
        comp_findings = [f for f in findings.items if f["component"] == comp]
        sev = max((SEV_ORDER.get(f["severity"], 0) for f in comp_findings), default=0)
        status = {0: "green", 1: "yellow", 2: "red"}[sev]
        why = [f["title"] for f in comp_findings if f["severity"] in ("red", "yellow")]
        metrics = {}
        if comp == "lab":
            metrics = {"worker_status": w_status, "worker_age_s": w_age,
                       "queue_total": sum(queue_counts.values()),
                       "strategies_7d": strat_7d_total or 0}
        elif comp == "shadow":
            metrics = {"n_trades_30d": kpis_30d["n"],
                       "net_30d": _round2(kpis_30d["net"]),
                       "n_deployed": n_deployed,
                       "decay_counts": decay_counts or {}}
        elif comp == "demo_live":
            metrics = {"equity_total": total_equity, "pnl_7d": kpi_7d,
                       "open_positions": pos_open_total,
                       "tca_p90_bps": tca_p90, "n_bots": len(fleet),
                       "n_live": sum(1 for b in fleet if b["is_live"])}
        elif comp == "risk":
            metrics = {"blocked_bots": sum(1 for b in fleet if b["blocked"]),
                       "max_dd_pct": max([abs(b["dd_pct"]) for b in fleet
                                          if b["dd_pct"] is not None], default=None),
                       "n_l1": sum(1 for b in fleet if b["dd_level"] == 1),
                       "l1_alert_pct": guard_l1, "l2_block_pct": guard_l2}
        elif comp == "data":
            metrics = {"feed_age_s": _i(feed_age), "market_open": mkt_open,
                       "pipeline_age_s": _i(pipeline_age)}
        components[comp] = {"status": status, "why": why, "metrics": metrics}

    overall_sev = max((SEV_ORDER.get(f["severity"], 0) for f in findings.items
                       if f["severity"] in ("red", "yellow")), default=0)
    overall_status = {0: "green", 1: "yellow", 2: "red"}[overall_sev]
    n_red = sum(1 for f in findings.items if f["severity"] == "red")
    n_yellow = sum(1 for f in findings.items if f["severity"] == "yellow")
    if overall_status == "red":
        headline = f"ROT: {n_red} kritische Findings"
    elif overall_status == "yellow":
        headline = f"GELB: {n_yellow} " + ("Warnung" if n_yellow == 1 else "Warnungen")
    else:
        headline = "GRÜN: alle Komponenten unauffällig"
    overall_why = [f["title"] for f in findings.sorted()
                   if f["severity"] in ("red", "yellow")]

    doc = {
        "schema": SCHEMA,
        "generated_at_utc": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_bz": now_dt.astimezone(BERLIN_TZ).isoformat(timespec="seconds"),
        "market_open": mkt_open,
        "verdict": {
            "overall": {"status": overall_status, "headline": headline,
                        "why": overall_why},
            "components": components,
        },
        "findings": findings.sorted(),
        "live": {
            "kpis": live_kpis,
            "fleet": fleet,
            "total_equity_curve": total_curve_out,
        },
        "shadow": {
            "kpis": {"n_trades_30d": kpis_30d["n"],
                     "net_30d": _round2(kpis_30d["net"]),
                     "n_deployed": n_deployed},
            "ranking": ranking,
            "decay": {"counts": decay_counts, "rows": decay_rows},
            "challenges": challenges,
            "rotation": rotation,
        },
        "lab": lab_out,
        "charts": {
            "monthly_pnl": monthly_pnl,
            "tca_groups": tca_groups,
            "corr": {"labels": slot_sids, "matrix": matrix},
            "exposure": exposure,
            "pnl_daily_30d": pnl_daily_out,
        },
        "sources": sources.items,
    }
    return doc


# ══ CLI ═══════════════════════════════════════════════════════════════════════

def _write_atomic(path, doc):
    """Atomarer Write (tmp + os.replace, Muster smart_rebuild.py:203-208)."""
    directory = os.path.dirname(str(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    os.replace(tmp, str(path))


def main(argv=None):
    p = argparse.ArgumentParser(
        description="System-Overview Datenlayer (schema overview_v1) bauen")
    p.add_argument("--root", default="/root/.hermes/site",
                   help="Site-Dir (Default /root/.hermes/site)")
    p.add_argument("--fx-root", default="/root/fx-bot",
                   help="fx-bot-Root (Default /root/fx-bot)")
    p.add_argument("--sl-root", default="/root/strategy-lab",
                   help="strategy-lab-Root (Default /root/strategy-lab)")
    p.add_argument("--trading-data", default="/root/trading/data",
                   help="trading/data-Root (Default /root/trading/data)")
    p.add_argument("--out", default=None,
                   help="Output-Datei (Default <root>/api/overview/overview.json)")
    p.add_argument("--now", type=float, default=None,
                   help="Epoch-Sekunden für Determinismus (Default: jetzt)")
    opts = p.parse_args(argv)

    out_path = opts.out or os.path.join(opts.root, "api", "overview", "overview.json")
    doc = build(opts.root, opts.fx_root, opts.sl_root, opts.trading_data, now=opts.now)
    _write_atomic(out_path, doc)

    overall = doc["verdict"]["overall"]
    print(f"[build_overview_status] {out_path}")
    print(f"[build_overview_status] overall={overall['status']} "
          f"({overall['headline']}) | findings={len(doc['findings'])} "
          f"fleet={len(doc['live']['fleet'])} "
          f"sources={len(doc['sources'])} "
          f"market_open={doc['market_open']}")
    return doc


if __name__ == "__main__":
    main()