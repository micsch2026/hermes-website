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
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent
OUT = SITE / "api" / "missions" / "missions_status.json"
BASE = Path(os.environ.get("MISSION_DIR", "/root/strategy-lab/data/missions"))
LOG = BASE / "mission_log.jsonl"
PROPOSALS = BASE / "proposals.jsonl"

STATUS_ORDER = {"active": 0, "blocked": 0, "proposed": 1, "done": 2, "aborted": 3}


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


def _log_tails(max_lines: int = 600):
    tails = {}
    try:
        with open(LOG, encoding="utf-8") as fh:
            lines = fh.readlines()[-max_lines:]
    except OSError:
        return tails
    for ln in lines:
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
        tails.setdefault(mid, []).append({
            "ts": e.get("ts"), "event": e.get("event"), "text": e.get("text"),
            "stage": e.get("stage"),
        })
    return {k: v[-6:] for k, v in tails.items()}


def main():
    missions = []
    for f in sorted(BASE.glob("m*.json")):
        m = _read_json(f)
        if not m or not m.get("mission_id"):
            continue
        stages = m.get("stages", [])
        done = sum(1 for s in stages if s.get("status") == "done")
        total = len(stages)
        missions.append({
            "id": m.get("mission_id"), "title": m.get("title"),
            "status": m.get("status"), "goal": (m.get("goal") or "")[:400],
            "budget": m.get("budget") or {},
            "created_at": m.get("created_at"), "updated_at": m.get("updated_at"),
            "done": done, "total": total,
            "pct": round(100 * done / total) if total else 0,
            "stages": [{
                "id": s.get("id"), "title": s.get("title"), "type": s.get("type"),
                "owner": s.get("owner"), "status": s.get("status"),
                "gate": s.get("gate"), "evidence": s.get("evidence") or [],
                "blocker": s.get("blocker"), "notes": s.get("notes"),
            } for s in stages],
            "log_tail": [],
        })

    tails = _log_tails()
    for m in missions:
        m["log_tail"] = tails.get(m["id"], [])

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
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
