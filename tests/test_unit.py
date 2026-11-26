"""Offline tests (no Flagsmith needed): python3 -m unittest tests/test_unit.py"""
import json, os, subprocess, sys, tempfile, unittest
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(R, "skills/flagsmith-migrate-parity/scripts/fsmig.py")
FL = os.path.join(R, "examples/legacy-app/flags.json")
sys.path.insert(0, os.path.dirname(F)); import fsmig


def run(*a):
    p = subprocess.run([sys.executable, F, *a], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


class T(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()

    def mkplan(self, flags=FL, mode="preserve"):
        out = os.path.join(self.d, "plan.json"); run("plan", "--flags", flags, "--mode", mode, "--out", out); return out

    def mkres(self, **kw):
        r = {"verdict": "PARITY_ON_SAMPLE", "mode": "preserve", "flags_sha": fsmig.file_sha(FL), "plan_hash": json.load(open(self.mkplan()))["hash"]}
        r.update(kw); p = os.path.join(self.d, "res.json"); json.dump(r, open(p, "w")); return p

    def test_unsupported_operator_is_never_planned(self):
        f = os.path.join(self.d, "f.json"); json.dump({"flags": [{"name": "x", "rules": [{"attribute": "a", "operator": "regex", "value": "."}]}]}, open(f, "w"))
        rc, out = run("inventory", "--flags", f); self.assertIn("x", out["unsupported"])
        self.assertEqual(json.load(open(self.mkplan(f)))["steps"], [])

    def test_plan_is_deterministic_and_modes_differ(self):
        a = json.load(open(self.mkplan())); b = json.load(open(self.mkplan()))
        self.assertEqual(a["hash"], b["hash"]); self.assertNotEqual(a["hash"], json.load(open(self.mkplan(mode="native")))["hash"])

    def test_preserve_uses_trait_native_uses_percentage_split(self):
        self.assertIn("LESS_THAN", json.dumps(json.load(open(self.mkplan()))["steps"]))
        n = json.dumps(json.load(open(self.mkplan(mode="native")))["steps"]); self.assertIn("PERCENTAGE_SPLIT", n); self.assertIn("$.identity.key", n)

    def test_apply_refuses_wrong_hash_without_touching_cli(self):
        rc, out = run("apply", "--plan", self.mkplan(), "--approve-hash", "000000000000", "--project", "1", "--environment", "x", "--cli", "/nonexistent")
        self.assertEqual(rc, 2); self.assertIn("does not match", out["error"])

    def test_gate_open_only_for_matching_parity(self):
        plan = self.mkplan()
        rc, out = run("gate", "--flags", FL, "--plan", plan, "--result", self.mkres()); self.assertEqual((rc, out["gate"]), (0, "OPEN_FOR_HUMAN_APPROVAL"))

    def test_gate_closed_when_flags_left_unmigrated(self):
        f = os.path.join(self.d, "u.json"); json.dump({"flags": [{"name": "a"}, {"name": "x", "rules": [{"attribute": "a", "operator": "regex", "value": "."}]}]}, open(f, "w"))
        plan = os.path.join(self.d, "pu.json"); run("plan", "--flags", f, "--out", plan)
        res = os.path.join(self.d, "ru.json"); json.dump({"verdict": "PARITY_ON_SAMPLE", "mode": "preserve", "flags_sha": fsmig.file_sha(f), "plan_hash": json.load(open(plan))["hash"]}, open(res, "w"))
        rc, out = run("gate", "--flags", f, "--plan", plan, "--result", res); self.assertEqual(rc, 1); self.assertTrue(any("unmigrated" in w for w in out["why"]))

    def test_gate_closed_cases(self):
        plan = self.mkplan()
        for kw, frag in [({"verdict": "MISMATCHES"}, "verdict"), ({"plan_hash": "abc"}, "not run for this plan"), ({"flags_sha": "abc"}, "changed"), ({"mode": "native"}, "mode")]:
            rc, out = run("gate", "--flags", FL, "--plan", plan, "--result", self.mkres(**kw))
            self.assertEqual(rc, 1, kw); self.assertTrue(any(frag in w for w in out["why"]), (kw, out))

    def test_gate_open_when_everything_matches(self):
        f = os.path.join(self.d, "f.json"); json.dump({"flags": [{"name": "a", "enabled": True}, {"name": "r", "rollout_percent": 10}]}, open(f, "w"))
        plan = os.path.join(self.d, "p.json"); run("plan", "--flags", f, "--out", plan)
        res = os.path.join(self.d, "r.json"); json.dump({"verdict": "PARITY_ON_SAMPLE", "mode": "preserve", "flags_sha": fsmig.file_sha(f), "plan_hash": json.load(open(plan))["hash"]}, open(res, "w"))
        rc, out = run("gate", "--flags", f, "--plan", plan, "--result", res); self.assertEqual((rc, out["gate"]), (0, "OPEN_FOR_HUMAN_APPROVAL"))
        rc, out = run("gate", "--flags", f, "--plan", plan, "--result", os.path.join(self.d, "missing.json")); self.assertEqual(rc, 2)

    def test_legacy_bucket_is_stable(self):
        sys.path.insert(0, os.path.join(R, "examples/legacy-app")); import legacy_flags
        self.assertEqual(legacy_flags.bucket("fast-search", "user-1"), legacy_flags.bucket("fast-search", "user-1"))


if __name__ == "__main__":
    unittest.main()
