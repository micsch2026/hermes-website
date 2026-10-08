#!/usr/bin/env python3
"""Tests fuer build_missions_status.py (Datenlayer /missions, Schema missions_v1).

Isoliert: MISSION_DIR + MISSIONS_OUT auf temp — schreibt NIE in api/.
Ausfuehrung: cd /root/.hermes/site && /usr/bin/python3 tests/test_build_missions.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
BUILDER = SITE / "build_missions_status.py"


def _m(mid, status, stages):
    return {"mission_id": mid, "title": mid, "status": status, "goal": "g " + mid,
            "created_at": "2026-10-08T00:00:00+00:00",
            "updated_at": "2026-10-08T01:00:00+00:00",
            "stages": stages}


class TestBuildMissions(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="missions-builder-test-"))
        staging = [
            _m("m-a", "active", [
                {"id": "s1", "title": "Daten", "type": "data", "status": "done",
                 "evidence": ["/x"]},
                {"id": "s2", "title": "Lab", "type": "lab", "status": "blocked",
                 "gate": {"kind": "classes_onboarding", "state": "pending", "reason": "r"}}]),
            _m("m-b", "proposed",
               [{"id": "s1", "title": "t", "type": "research", "status": "pending"}]),
        ]
        for m in staging:
            (self.td / f"{m['mission_id']}.json").write_text(
                json.dumps(m), encoding="utf-8")
        (self.td / "mission_log.jsonl").write_text(
            json.dumps({"ts": "2026-10-08T01:00:00+00:00", "mission_id": "m-a",
                        "event": "stage", "text": "s1 done"}) + "\n", encoding="utf-8")
        (self.td / "proposals.jsonl").write_text(
            json.dumps({"ts": "2026-10-08T00:30:00+00:00", "by": "board", "title": "P",
                        "goal": "G", "status": "open"}) + "\n", encoding="utf-8")
        self.out = self.td / "out" / "missions.json"

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def build(self):
        env = dict(os.environ, MISSION_DIR=str(self.td), MISSIONS_OUT=str(self.out))
        env.pop("PYTHONPATH", None)
        r = subprocess.run([sys.executable or "/usr/bin/python3", str(BUILDER)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_schema_and_kpis(self):
        d = self.build()
        self.assertEqual(d["schema"], "missions_v1")
        k = d["kpis"]
        self.assertEqual(k["active"], 1)
        self.assertEqual(k["proposed"], 1)
        self.assertEqual(k["gates_open"], 1)
        self.assertEqual(k["stages_done"], 1)
        self.assertEqual(k["stages_total"], 2)

    def test_order_active_before_proposed(self):
        d = self.build()
        ids = [m["id"] for m in d["missions"]]
        self.assertEqual(ids, ["m-a", "m-b"])
        self.assertEqual(d["missions"][0]["pct"], 50)
        self.assertEqual(d["missions"][1]["pct"], 0)

    def test_log_tail_and_proposals(self):
        d = self.build()
        self.assertEqual(len(d["missions"][0]["log_tail"]), 1)
        self.assertEqual(d["missions"][1]["log_tail"], [])
        self.assertEqual(len(d["proposals"]), 1)
        self.assertEqual(d["proposals"][0]["by"], "board")

    def test_sources_and_atomic_output(self):
        d = self.build()
        self.assertEqual([s["name"] for s in d["sources"]],
                         ["missions", "mission_log", "proposals"])
        self.assertTrue(self.out.exists())
        self.assertFalse(self.out.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
