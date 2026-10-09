#!/usr/bin/env python3
"""Tests fuer build_supervisor_status.py (Datenlayer /supervisor, schema supervisor_v1).

Isoliert: SUPERVISOR_OUT + SB_DIR/OPS_DIR/FX_DIR/MISSION_DIR auf temp-Fixtures —
schreibt NIE in api/. Ausfuehrung: cd site && /usr/bin/python3 tests/test_build_supervisor.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
BUILDER = SITE / "build_supervisor_status.py"


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


class TestBuildSupervisor(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="supervisor-builder-test-"))
        self.sb = self.td / "sb"
        self.ops = self.td / "ops"
        self.fx = self.td / "fx"
        self.mi = self.td / "mi"
        self.out = self.td / "out" / "supervisor.json"
        now = datetime.now(timezone.utc)

        # --- Strategy-Board ---
        _write(self.sb / "weekly_review_2026-W41.json", {
            "week": "2026-W41",
            "recommendations": {"n": 1, "items": [
                {"source": "advisor", "target": "bot1/main", "action": "pull",
                 "priority": "high", "text": "X"}]},
            "portfolio": {"demo": {"bots": [{"bot": "bot1", "pnl7d": 1.0}]}},
            "live_accounts": {"bots": [{"bot": "bot9", "balance": 100.0,
                                        "parity_state": "ok"}]},
            "lever": {"milestones_top": []}, "costs": {}, "macro": {}, "notes": [],
        })
        _write(self.sb / "applied_2026-W41.json", {
            "applied_at": "2026-10-04T01:02:07+00:00",
            "seeds_new": ["a", "b"],
            "seeds_skipped": [],
            "cluster_edits": [["recipe_clusters.json", "c1", "a"]],
            "tiers_added": ["c1"],
            "retires_applied": ["old"],
            "watches_added": [{"sid": 1, "kind": "debug"}],
            "watches_closed": [],
        })
        _write(self.sb / "gate_evidence_2026-W41.json", {"generated_at": None, "candidates": []})
        cj_lines = []
        for i in range(3):
            ts = (now - timedelta(days=i)).isoformat(timespec="seconds")
            cj_lines.append(json.dumps({"ts_recorded": ts, "typ": "seed", "key": "k",
                                        "datum": "2026-10-04"}))
        (self.sb / "change_journal.jsonl").write_text(
            "\n".join(cj_lines) + "\n", encoding="utf-8")

        # --- Ops ---
        _write(self.ops / "state.json", {"known": {}, "resolved_recent": [],
                                         "last_run_utc": "2026-10-09T10:20:36+00:00"})

        # --- FX / Rotation ---
        (self.fx / "data" / "rotation").mkdir(parents=True, exist_ok=True)
        (self.fx / "data" / "bot3_slot_history.jsonl").write_text("", encoding="utf-8")
        (self.fx / "data" / "rotation" / "rotation_log.jsonl").write_text("", encoding="utf-8")

        # --- Missionen ---
        _write(self.mi / "m-x.json", {
            "mission_id": "m-x", "title": "X", "status": "active", "goal": "g",
            "stages": [
                {"id": "s1", "title": "Gate", "type": "dev", "status": "pending",
                 "gate": {"kind": "k", "state": "pending", "reason": "r"}}],
        })
        (self.mi / "proposals.jsonl").write_text(json.dumps(
            {"title": "P", "goal": "G", "by": "board", "status": "open"}) + "\n",
            encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def build(self):
        env = dict(os.environ,
                   SUPERVISOR_OUT=str(self.out),
                   SB_DIR=str(self.sb), OPS_DIR=str(self.ops),
                   FX_DIR=str(self.fx), MISSION_DIR=str(self.mi))
        env.pop("PYTHONPATH", None)
        r = subprocess.run([sys.executable or "/usr/bin/python3", str(BUILDER)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_schema_and_next_board_run(self):
        d = self.build()
        self.assertEqual(d["schema"], "supervisor_v1")
        self.assertIn("next_board_run", d)
        nbr = datetime.fromisoformat(d["next_board_run"])
        self.assertGreater(nbr, datetime.now(timezone.utc))

    def test_autonomy_applied_numbers(self):
        d = self.build()
        au = d["autonomy"]
        self.assertEqual(au["week"], "2026-W41")
        ap = au["applied"]
        for k in ("seeds", "cluster_edits", "tiers", "retires", "watches", "rotation_fills"):
            self.assertIn(k, ap)
            self.assertIsInstance(ap[k], int)
        self.assertEqual(ap["seeds"], 2)
        self.assertEqual(ap["cluster_edits"], 1)
        self.assertEqual(ap["tiers"], 1)
        self.assertEqual(ap["retires"], 1)
        self.assertEqual(ap["watches"], 1)

    def test_waiting_user_consistent_with_gates(self):
        d = self.build()
        wu = d["autonomy"]["waiting_user"]
        self.assertEqual(wu["gates_open"], 1)
        self.assertEqual(wu["proposals_open"], 1)
        items = wu["items"]
        self.assertLessEqual(len(items), 5)
        self.assertEqual(items[0]["kind"], "gate")
        self.assertEqual(items[0]["mission"], "m-x")
        self.assertEqual(items[0]["stage"], "s1")
        self.assertEqual(items[0]["reason"], "r")

    def test_activity_and_atomic_output(self):
        d = self.build()
        act = d["activity"]
        self.assertEqual(len(act), 14)
        self.assertTrue(all(isinstance(x, int) for x in act))
        self.assertEqual(sum(act), 3)
        self.assertTrue(self.out.exists())
        self.assertFalse((self.out.parent / (self.out.name + ".tmp")).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
