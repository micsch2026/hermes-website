#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemeinsamer B6-/Repair-Status für Supervisor, Missions und Stratege."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LAB = Path("/root/strategy-lab")
LATEST = LAB / "data" / "deep_pass" / "latest.json"
POLICY = LAB / "data" / "deep_pass" / "policy.json"
DB = LAB / "catalog.db"


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_b6_status() -> dict:
    latest = _load(LATEST, {}) or {}
    policy = _load(POLICY, {}) or {}
    active = bool(policy.get("enabled_for_admission"))
    ea = policy.get("enforce_after")
    if not active and ea:
        try:
            d = datetime.fromisoformat(str(ea).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            active = datetime.now(timezone.utc) >= d
        except Exception:
            pass
    counts, reviewed, ready, repair = {}, 0, [], []
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        rows = c.execute("""
            SELECT cr.strategy_id, cr.verdict, cr.score, s.name
            FROM candidate_reviews cr
            JOIN strategies s ON s.id = cr.strategy_id
            JOIN (SELECT strategy_id, MAX(id) AS mid
                  FROM candidate_reviews GROUP BY strategy_id) x
              ON cr.id = x.mid
        """).fetchall()
        c.close()
        for r in rows:
            v = str(r["verdict"])
            counts[v] = counts.get(v, 0) + 1
            reviewed += 1
            item = {"id": int(r["strategy_id"]), "name": r["name"],
                    "score": r["score"], "verdict": v}
            if v == "shadow_ready":
                ready.append(item)
            elif v == "repair":
                repair.append(item)
    except Exception:
        pass
    repair_runs = []
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        repair_runs = [dict(r) for r in c.execute(
            "SELECT parent_id, variant_id, dimension, status, created_at "
            "FROM repair_runs ORDER BY id DESC LIMIT 8").fetchall()]
        c.close()
    except Exception:
        pass
    return {
        "available": bool(latest) or reviewed > 0,
        "generated_at": latest.get("generated_at"),
        "run_id": latest.get("run_id"),
        "active": active,
        "enforce_after": ea,
        "reviewed": reviewed,
        "counts": counts,
        "ready": ready,
        "repair": repair,
        "repair_runs": repair_runs,
        "next_repair_run": "täglich 03:40 BZ (idle-gated)",
        "note": "B6 ist das Eingangs-Gate; der Shadow-Bestand bleibt unberührt.",
    }
