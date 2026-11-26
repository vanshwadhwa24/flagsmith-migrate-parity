#!/usr/bin/env python3
"""Replay oracle for the example app. stdin: JSON lines {id, attrs}. stdout: JSON lines
{id, flags: {name: {enabled, value}}, buckets: {name: int}} computed by the legacy code itself.
`buckets` is the legacy bucket for every rollout flag: it is what a migrated client must send as a trait."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legacy_flags import bucket, evaluate

flags = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags.json")))["flags"]
for line in sys.stdin:
    q = json.loads(line)
    out = {"id": q["id"], "flags": {}, "buckets": {}}
    for f in flags:
        out["flags"][f["name"]] = {"enabled": evaluate(f, q["id"], q["attrs"]), "value": f.get("value")}
        if "rollout_percent" in f:
            out["buckets"][f["name"]] = bucket(f["name"], q["id"])
    print(json.dumps(out))
