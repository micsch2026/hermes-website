#!/usr/bin/env python3
"""build_supervisor_status.py — Supervisor-Datenlayer fuer die Seite /supervisor.

Read-only Aggregation der Selbststeuerungs-Ebene:
  strategy_board: weekly_review, impact, applied, gate_evidence, change_journal
  ops_review:     state.json + latest.md
  rotation:       rotation_log.jsonl + botN_slot_history.jsonl (Wirksamkeit)

Schreibt atomar api/supervisor/supervisor_status.json (schema supervisor_v1).
Kein LLM, keine Seiteneffekte auf die Quellen — reine Projektion.

Usage: python3 build_supervisor_status.py [--print-keys]
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover - Fallback ohne tz-Datenbank
    BERLIN = timezone(timedelta(hours=2))

SITE = Path(__file__).resolve().parent
SB = Path(os.environ.get("SB_DIR", "/root/strategy-lab/data/strategy_board"))
OPS = Path(os.environ.get("OPS_DIR", "/root/.hermes/reports/ops_review"))
FX = Path(os.environ.get("FX_DIR", "/root/fx-bot"))
MDIR = Path(os.environ.get("MISSION_DIR", "/root/strategy-lab/data/missions"))
OUT = Path(os.environ.get("SUPERVISOR_OUT",
                         SITE / "api" / "supervisor" / "supervisor_status.json"))

NOW = datetime.now(timezone.utc)

AUTONOMY_DAYS = 14


def _gate_dict(s):
    """Tolerantes Gate-Feld: dict unveraendert; String -> {kind, not_requested}; sonst {}."""
    g = (s or {}).get("gate")
    if isinstance(g, dict):
        return g
    if isinstance(g, str) and g.strip():
        return {"kind": g.strip(), "state": "not_requested"}
    return {}


def _next_board_run(now: datetime) -> str:
    """Naechster Strategy-Board-Lauf: Sonntag 03:00 Europe/Berlin -> ISO UTC."""
    b = now.astimezone(BERLIN)
    days_ahead = (6 - b.weekday()) % 7  # Sonntag == 6
    cand = datetime.combine(b.date() + timedelta(days=days_ahead),
                            time(3, 0), tzinfo=BERLIN)
    if cand <= b:
        cand += timedelta(days=7)
    return cand.astimezone(timezone.utc).isoformat(timespec="seconds")


def _activity(entries, ts_key, now: datetime, days: int = AUTONOMY_DAYS):
    """14 Ganzzahlen je Berlin-Kalendertag (aeltester zuerst)."""
    today = now.astimezone(BERLIN).date()
    buckets = [today - timedelta(days=days - 1 - i) for i in range(days)]
    counts = {d: 0 for d in buckets}
    for e in entries:
        ts = _parse_ts(e.get(ts_key))
        if ts is None:
            continue
        d = datetime.fromtimestamp(ts, timezone.utc).astimezone(BERLIN).date()
        if d in counts:
            counts[d] += 1
    return [counts[d] for d in buckets]


def _auto_releases(log: Path, now: datetime) -> dict:
    """Stufe-2-Auto-Freigaben der laufenden ISO-Woche (UTC) aus dem mission_log."""
    y, w, _ = now.astimezone(timezone.utc).isocalendar()
    wk = f"{y}-W{w:02d}"
    out = {"week": wk, "gates": 0, "proposals": 0, "refused": 0}
    try:
        with open(log, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if e.get("auto") is not True:
                    continue
                ts = _parse_ts(e.get("ts"))
                if ts is None:
                    continue
                yy, ww, _ = datetime.fromtimestamp(ts, timezone.utc).isocalendar()
                if f"{yy}-W{ww:02d}" != wk:
                    continue
                ev = e.get("event")
                if ev == "gate_approved":
                    out["gates"] += 1
                elif ev == "proposal_approved":
                    out["proposals"] += 1
                elif ev == "auto_release_refused":
                    out["refused"] += 1
    except OSError:
        pass
    return out


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _age_s(path, now: datetime):
    try:
        return round(now.timestamp() - os.path.getmtime(path))
    except OSError:
        return None


def _parse_ts(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _atomic_write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _regionen_kpi(fx: Path, now: datetime) -> dict:
    """Regionen-KPI bot5 (Mission m20261008 · Fill-Policy F1A, 20.10.2026).

    Soll = Baender aus fx/config/index_regions.json (SSOT, dieselbe Datei wie der
    Executor-Tiebreak); Ist = offene Positionen (positions_live) + Fills 7 d
    (bot5_trades, Region per symbol_to_region). Read-only, tolerant: fehlende
    Dateien/Config => leere Ist-Werte, kein Fehler.
    """
    cfg_path = Path(os.environ.get("FX_REGIONS_CONFIG",
                                   str(fx / "config" / "index_regions.json")))
    cfg = _read_json(cfg_path, {}) or {}
    smap = cfg.get("symbol_to_region") or {}
    bands = cfg.get("bands") or {}
    order = cfg.get("region_order") or {"ASIA": 0, "EU": 1, "US": 2}
    regions = [r for r, _ in sorted(order.items(), key=lambda kv: kv[1])]
    now_ts = now.timestamp()
    fills = {r: 0 for r in regions}
    netto = {r: 0.0 for r in regions}
    unmapped = 0
    try:
        with open(fx / "data" / "bot5_trades.jsonl", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                ts = _parse_ts(e.get("timestamp") or e.get("open_timestamp"))
                if ts is None or now_ts - ts > 7 * 86400:
                    continue
                r = smap.get(str(e.get("symbol") or ""))
                if r is None:
                    unmapped += 1
                    continue
                if r not in fills:
                    continue
                fills[r] += 1
                v = e.get("cTrader_profit")
                if v is None:
                    v = e.get("pnl")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    netto[r] += float(v)
    except OSError:
        pass
    openct = {r: 0 for r in regions}
    try:
        raw = _read_json(fx / "data" / "bot5_positions_live.json", []) or []
        if isinstance(raw, dict):
            raw = raw.get("positions") or []
        for p in raw:
            r = smap.get(str((p or {}).get("symbol") or ""))
            if r in openct:
                openct[r] += 1
    except OSError:
        pass
    ist = []
    for r in regions:
        b = bands.get(r) or {}
        ziel = int(b.get("ziel", 1) or 1)
        ist.append({
            "region": r, "open": openct.get(r, 0), "fills_7d": fills.get(r, 0),
            "netto_7d": round(netto.get(r, 0.0), 2),
            "soll_min": b.get("min"), "soll_max": b.get("max"), "ziel": ziel,
            "unter_ziel": openct.get(r, 0) < ziel,
        })
    return {
        "bot": "bot5", "as_of": _iso(now), "window_days": 7,
        "regions": regions, "ist": ist, "unmapped_7d": unmapped,
        "config_ok": bool(smap and bands),
        "status": "unter_ziel" if any(x["unter_ziel"] for x in ist) else "ok",
    }


def main() -> int:
    sources = []

    def src(name, path, cadence_s):
        p = Path(path)
        age = _age_s(p, NOW)
        sources.append({
            "name": name, "path": str(p), "age_s": age,
            "cadence_s": cadence_s,
            "ok": p.exists(),
            "fresh": (age is not None and age <= cadence_s * 1.5),
        })

    # ---- Wochen-Artefakte (neueste Review-Woche) ----
    weeks = sorted(SB.glob("weekly_review_2026-W*.json"), key=os.path.getmtime)
    wr_path = weeks[-1] if weeks else None
    week = wr_path.name.replace("weekly_review_", "").replace(".json", "") if wr_path else None
    wr = _read_json(wr_path, {}) if wr_path else {}
    imp_path = SB / f"impact_{week}.json" if week else None
    ap_path = SB / f"applied_{week}.json" if week else None
    ge_path = SB / f"gate_evidence_{week}.json" if week else None
    # Applied: der woechentliche Job schreibt je Zyklus ein NEUES Manifest; die
    # Loop-Frische am NEUESTEN Manifest messen (das review-wochen-gekoppelte File
    # ist per Konvention schon vor Wochenstart geschrieben und erzeugte sonst
    # False-STALE nach dem Apply der Folgewoche; Konvention 13.10.).
    ap_manifests = sorted(SB.glob("applied_2026-W*.json"))
    ap_fresh_path = ap_manifests[-1] if ap_manifests else ap_path
    for n, p in (("weekly_review", wr_path), ("impact", imp_path),
                 ("applied", ap_fresh_path), ("gate_evidence", ge_path)):
        if p:
            src(n, p, 7 * 86400)

    # ---- change_journal ----
    cj_path = SB / "change_journal.jsonl"
    src("change_journal", cj_path, 7 * 86400)
    cj = []
    try:
        with open(cj_path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    cj.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        pass
    by_typ = Counter(str(e.get("typ")) for e in cj)
    recent = sorted(cj, key=lambda e: str(e.get("ts_recorded", "")))[-10:]
    applied_raw = _read_json(ap_path, {}) if ap_path else {}

    # ---- Rotation-Wirksamkeit ----
    rl_path = FX / "data" / "rotation" / "rotation_log.jsonl"
    # 13.10.26: Rotation laeuft TAEGLICH (06:12 BZ) — die alte 6h-Kadenz erzeugte
    # False-STALE fuer ~18h/Tag. 24h-Kadenz (+1.5x Freshness-Faktor = 36h Fenster).
    src("rotation_log", rl_path, 24 * 3600)
    runs7, refused7 = set(), 0
    now_ts = NOW.timestamp()
    try:
        with open(rl_path, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                ts = _parse_ts(e.get("ts"))
                if ts is not None and now_ts - ts <= 7 * 86400:
                    runs7.add(str(e.get("run_id")))
                    if str(e.get("action", "")).startswith("apply_refused"):
                        refused7 += 1
    except OSError:
        pass
    fills14, last_fill = 0, None
    sh_files = sorted(FX.glob("data/bot*_slot_history.jsonl"))
    # 13.10.26: NEUESTE Datei nach mtime zaehlt (alphabetisch letzte war z.B. bot8
    # und 60h alt = False-STALE trotz frischem bot7-Schreibzugriff). Slot-Uebergaenge
    # sind ereignisbasiert → Kadenz 72h (Freshness-Fenster 108h).
    _sh_newest = max(sh_files, key=os.path.getmtime) if sh_files else FX / "data" / "bot3_slot_history.jsonl"
    src("slot_history", _sh_newest, 72 * 3600)
    for f in sh_files:
        try:
            with open(f, encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        e = json.loads(ln)
                    except ValueError:
                        continue
                    if e.get("reason") == "rotation" and e.get("note") == "fill":
                        ts = _parse_ts(e.get("from"))
                        if ts is not None and now_ts - ts <= 14 * 86400:
                            fills14 += 1
                            if last_fill is None or ts > last_fill[0]:
                                last_fill = (ts, e.get("bot"), e.get("slot_id"),
                                             e.get("strategy_id"))
        except OSError:
            continue
    rotation = {
        "runs_7d": len(runs7),
        "refused_7d": refused7,
        "fills_14d": fills14,
        "last_fill": None if last_fill is None else {
            "ts": _iso(datetime.fromtimestamp(last_fill[0], timezone.utc)),
            "bot": last_fill[1], "slot": last_fill[2], "sid": last_fill[3]},
    }

    # ---- L5 Multibot-Portfolio-Review (12.10.2026) ----
    pr_path = FX / "data" / "rotation" / "portfolio_review.json"
    src("portfolio_review", pr_path, 7 * 86400)
    prj = _read_json(pr_path, {}) or {}
    portfolio_review = {
        "generated_at": prj.get("generated"),
        "findings": (prj.get("findings") or [])[:6],
        "open_recs_aged": [r for r in (prj.get("open_recommendations") or [])
                           if r.get("level") in ("warn", "alert")][:5],
        "tracking_error_flags": [r for r in (prj.get("tracking_error") or [])
                                 if r.get("delta_own_vs_live") is not None
                                 and abs(r["delta_own_vs_live"]) > 30][:5],
        "challenge_kpi": prj.get("challenge_kpi"),
    }

    # ---- Regionen-KPI (Index-Fill-Policy F1A, Mission m20261008, 20.10.2026) ----
    rk_cfg_path = Path(os.environ.get("FX_REGIONS_CONFIG",
                                      str(FX / "config" / "index_regions.json")))
    src("index_regions_config", rk_cfg_path, 30 * 86400)
    src("bot5_dashboard", SITE / "api" / "bot5" / "dashboard.json", 600)
    regionen_kpi = _regionen_kpi(FX, NOW)

    # ---- Ops-Review ----
    ops_path = OPS / "state.json"
    src("ops_review", ops_path, 2 * 3600)
    ops_state = _read_json(ops_path, {}) or {}
    known = ops_state.get("known") or {}
    ops = {
        "last_run_utc": ops_state.get("last_run_utc"),
        "last_green": ops_state.get("last_green_msg"),
        "open_issues": [
            {"key": k, **(v if isinstance(v, dict) else {})}
            for k, v in known.items()
        ][:10],
        "resolved_recent_n": len(ops_state.get("resolved_recent") or []),
    }

    # ---- Empfehlungen + Wochen-Review-Subset ----
    recs = wr.get("recommendations") or {"n": 0, "items": []}
    geo = _read_json(ge_path, {}) if ge_path else {}
    weekly = {
        "portfolio": wr.get("portfolio") or {},
        "live_accounts": wr.get("live_accounts") or {},
        "lever": wr.get("lever") or {},
        "costs": wr.get("costs") or {},
        "macro": wr.get("macro") or {},
        "notes": wr.get("notes") or [],
    }

    # ---- Missionen (Supervisor-Missionslayer) ----
    mdir = MDIR
    src("missions", mdir, 24 * 3600)
    missions_active, missions_proposed = [], []
    for f in sorted(mdir.glob("m*.json")):
        mm = _read_json(f, {}) or {}
        if not mm.get("mission_id"):
            continue
        # Support-Dokumente (*-kohorte.json) haben kein stages-Schema -> skip.
        if not isinstance(mm.get("stages"), list):
            continue
        stages = mm.get("stages", [])
        item = {
            "id": mm.get("mission_id"), "title": mm.get("title"),
            "status": mm.get("status"), "goal": (mm.get("goal") or "")[:220],
            "done": sum(1 for s in stages if s.get("status") == "done"),
            "total": len(stages),
            "stages": [{"id": s.get("id"), "title": s.get("title"), "type": s.get("type"),
                        "status": s.get("status"),
                        "gate_kind": _gate_dict(s).get("kind"),
                        "gate_state": _gate_dict(s).get("state")}
                       for s in stages],
            "gates_open": [{"stage": s.get("id"),
                            "kind": _gate_dict(s).get("kind"),
                            "reason": _gate_dict(s).get("reason")}
                           for s in stages
                           if _gate_dict(s).get("state") == "pending"],
        }
        if mm.get("status") in ("active", "blocked"):
            missions_active.append(item)
        elif mm.get("status") == "proposed":
            missions_proposed.append(item)
    proposals_open = []
    try:
        with open(mdir / "proposals.jsonl", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    p = json.loads(ln)
                except ValueError:
                    continue
                if p.get("status") == "open":
                    proposals_open.append({"title": p.get("title"),
                                           "goal": (p.get("goal") or "")[:180],
                                           "by": p.get("by")})
    except OSError:
        pass

    # ---- Autonomie & naechste Schritte ----
    applied_counts = {
        "seeds": len(applied_raw.get("seeds_new") or []),
        "cluster_edits": len(applied_raw.get("cluster_edits") or []),
        "tiers": len(applied_raw.get("tiers_added") or []),
        "retires": len(applied_raw.get("retires_applied") or []),
        "watches": len(applied_raw.get("watches_added") or []),
        "rotation_fills": int(by_typ.get("rotation_fill", 0)),
    }
    gate_items = []
    for mm in missions_active:
        for gg in mm.get("gates_open", []):
            gate_items.append({"kind": "gate", "mission": mm.get("id"),
                               "stage": gg.get("stage"), "reason": gg.get("reason")})
    autonomy = {
        "week": week,
        "applied": applied_counts,
        "auto_releases": _auto_releases(mdir / "mission_log.jsonl", NOW),
        "waiting_user": {
            "gates_open": len(gate_items),
            "proposals_open": len(proposals_open),
            "items": gate_items[:5],
        },
    }
    next_board_run = _next_board_run(NOW)
    activity = _activity(cj, "ts_recorded", NOW)

    doc = {
        "schema": "supervisor_v1",
        "generated_at": _iso(NOW),
        "week": week,
        "next_board_run": next_board_run,
        "autonomy": autonomy,
        "activity": activity,
        "sources": sources,
        "rotation": rotation,
        "portfolio_review": portfolio_review,
        "regionen_kpi": regionen_kpi,
        "recommendations": recs,
        "weekly": weekly,
        "changes": {
            "total": len(cj),
            "by_typ": dict(by_typ),
            "recent": [
                {"typ": e.get("typ"), "key": e.get("key"), "datum": e.get("datum")}
                for e in recent
            ],
            "applied": {
                k: applied_raw.get(k)
                for k in ("applied_at", "seeds_new", "seeds_skipped", "cluster_edits",
                          "tiers_added", "focus", "cooldowns_reset", "retires_applied",
                          "retires_skipped", "watches_added", "watches_closed")
            },
        },
        "gate_evidence": {
            "generated_at": geo.get("generated_at"),
            "candidates": geo.get("candidates") or [],
        },
        "missions": {
            "active": missions_active,
            "proposed": missions_proposed,
            "proposals_open": proposals_open,
        },
        "ops": ops,
    }

    _atomic_write(OUT, doc)
    if "--print-keys" in sys.argv:
        print(json.dumps({k: (type(v).__name__) for k, v in doc.items()}, indent=1))
    print(f"OK {OUT} ({OUT.stat().st_size} bytes) week={week} "
          f"recs={recs.get('n')} changes={len(cj)} fills14={fills14} runs7={len(runs7)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
