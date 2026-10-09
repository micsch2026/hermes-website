#!/usr/bin/env python3
"""build_missions_status.py — Datenlayer der Seite /missions.

Liest den Missions-Store des Supervisor-Layers
(/root/strategy-lab/data/missions: m*.json + mission_log.jsonl + proposals.jsonl)
und schreibt api/missions/missions_status.json (Schema missions_v1, atomar).

Read-only bzgl. Quellen. ENV MISSION_DIR override (Tests).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover - Fallback ohne tz-Datenbank
    BERLIN = timezone(timedelta(hours=2))

SITE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("MISSIONS_OUT", SITE / "api" / "missions" / "missions_status.json"))
BASE = Path(os.environ.get("MISSION_DIR", "/root/strategy-lab/data/missions"))
LOG = BASE / "mission_log.jsonl"
PROPOSALS = BASE / "proposals.jsonl"

STATUS_ORDER = {"active": 0, "blocked": 0, "proposed": 1, "done": 2, "aborted": 3}

# Taegliche Runner-Slots (UTC) fuer die ETA-Schaetzung im Missionslayer.
RUNNER_SLOTS_UTC = (6, 11, 17)
ACTIVITY_DAYS = 14
LOG_TAIL_MAX = 8


def _parse_dt(raw):
    """ISO-String/Epoche -> aware datetime (UTC) oder None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return datetime.fromtimestamp(float(raw), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def next_runner_run(now=None):
    """Naechster Slot aus taeglich 06/11/17 UTC als aware datetime."""
    now = now or datetime.now(timezone.utc)
    for h in RUNNER_SLOTS_UTC:
        cand = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if cand > now:
            return cand
    nxt = (now + timedelta(days=1)).replace(hour=RUNNER_SLOTS_UTC[0],
                                            minute=0, second=0, microsecond=0)
    return nxt


def _activity(entries, now: datetime, days: int = ACTIVITY_DAYS):
    """14 Ganzzahlen: Log-Eintraege je Berlin-Kalendertag (aeltester zuerst)."""
    today = now.astimezone(BERLIN).date()
    buckets = [today - timedelta(days=days - 1 - i) for i in range(days)]
    counts = {d: 0 for d in buckets}
    for e in entries:
        dt = _parse_dt(e.get("ts"))
        if dt is None:
            continue
        d = dt.astimezone(BERLIN).date()
        if d in counts:
            counts[d] += 1
    return [counts[d] for d in buckets]


def _eta_hint(next_stage, next_run_iso):
    """Deutsche ETA-Kurzinfo nach fester Regelreihenfolge."""
    if not next_stage:
        return "—"
    if (next_stage.get("gate") or {}).get("state") == "pending":
        return "Wartet auf Freigabe"
    owner = next_stage.get("owner")
    if owner == "runner":
        return f"Runner: naechster Lauf {next_run_iso}"
    if owner == "system":
        return "System: laeuft kontinuierlich"
    return owner or ""


def _read_json(p: Path, default=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _age_s(p: Path):
    try:
        return int(time.time() - p.stat().st_mtime)
    except OSError:
        return None


def _read_log():
    """Alle Log-Eintraege (kleines JSONL) je Mission gruppiert, chronologisch."""
    grouped = {}
    try:
        with open(LOG, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                mid = e.get("mission_id")
                if not mid:
                    continue
                grouped.setdefault(mid, []).append(e)
    except OSError:
        return grouped
    return grouped


def main():
    now = datetime.now(timezone.utc)
    next_run = next_runner_run(now)
    next_run_iso = next_run.isoformat(timespec="seconds")

    log_by_mid = _read_log()

    missions = []
    for f in sorted(BASE.glob("m*.json")):
        m = _read_json(f)
        if not m or not m.get("mission_id"):
            continue
        stages_raw = m.get("stages", [])
        done = sum(1 for s in stages_raw if s.get("status") == "done")
        total = len(stages_raw)
        stages = [{
            "id": s.get("id"), "title": s.get("title"), "type": s.get("type"),
            "owner": s.get("owner"), "status": s.get("status"),
            "gate": s.get("gate"), "evidence": s.get("evidence") or [],
            "blocker": s.get("blocker"), "notes": s.get("notes"),
        } for s in stages_raw]

        entries = log_by_mid.get(m.get("mission_id"), [])
        log_tail = [{
            "ts": e.get("ts"), "event": e.get("event"), "text": e.get("text"),
            "stage": e.get("stage"),
        } for e in entries[-LOG_TAIL_MAX:]]

        # --- now: letzte erledigte / laufende / naechste Etappe ---
        done_stages = [s for s in stages if s.get("status") == "done"]
        running_stage = next((s for s in stages if s.get("status") == "running"), None)
        next_stage = next((s for s in stages if s.get("status") == "pending"), None)

        last_done = None
        if done_stages:
            last_done = {"id": done_stages[-1].get("id"),
                         "title": done_stages[-1].get("title")}
        running = None
        if running_stage:
            since = None
            rid = running_stage.get("id")
            for e in reversed(entries):
                if e.get("stage") == rid and e.get("ts"):
                    since = e.get("ts")
                    break
            if since is None:
                since = m.get("updated_at")
            running = {"id": rid, "title": running_stage.get("title"), "since": since}
        nxt = None
        if next_stage:
            nxt = {"id": next_stage.get("id"), "title": next_stage.get("title"),
                   "owner": next_stage.get("owner"),
                   "gate_state": (next_stage.get("gate") or {}).get("state")}

        missions.append({
            "id": m.get("mission_id"), "title": m.get("title"),
            "status": m.get("status"), "goal": (m.get("goal") or "")[:400],
            "budget": m.get("budget") or {},
            "created_at": m.get("created_at"), "updated_at": m.get("updated_at"),
            "done": done, "total": total,
            "pct": round(100 * done / total) if total else 0,
            "now": {"last_done": last_done, "running": running, "next": nxt},
            "eta_hint": _eta_hint(next_stage, next_run_iso),
            "activity": _activity(entries, now),
            "stages": stages,
            "log_tail": log_tail,
        })

    missions.sort(key=lambda x: (STATUS_ORDER.get(x["status"], 9), x["id"]))

    gates_open = sum(1 for m in missions if m["status"] in ("active", "blocked")
                     for s in m["stages"]
                     if (s.get("gate") or {}).get("state") == "pending")
    active = [m for m in missions if m["status"] in ("active", "blocked")]
    proposed = [m for m in missions if m["status"] == "proposed"]
    finished = [m for m in missions if m["status"] in ("done", "aborted")]
    prog_done = sum(m["done"] for m in active)
    prog_total = sum(m["total"] for m in active)

    proposals = []
    try:
        with open(PROPOSALS, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    p = json.loads(ln)
                except ValueError:
                    continue
                if p.get("status") == "open":
                    proposals.append({"title": p.get("title"),
                                      "goal": (p.get("goal") or "")[:220],
                                      "by": p.get("by"), "ts": p.get("ts")})
    except OSError:
        pass

    doc = {
        "schema": "missions_v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "next_runner_run": next_run_iso,
        "kpis": {
            "active": len(active), "proposed": len(proposed),
            "finished": len(finished), "gates_open": gates_open,
            "stages_done": prog_done, "stages_total": prog_total,
        },
        "missions": missions,
        "proposals": proposals,
        "sources": [
            {"name": "missions", "path": str(BASE), "age_s": _age_s(BASE)},
            {"name": "mission_log", "path": str(LOG), "age_s": _age_s(LOG)},
            {"name": "proposals", "path": str(PROPOSALS), "age_s": _age_s(PROPOSALS)},
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    print(f"OK {OUT} ({OUT.stat().st_size} bytes) aktiv={len(active)} "
          f"proposed={len(proposed)} gates={gates_open} done={len(finished)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
