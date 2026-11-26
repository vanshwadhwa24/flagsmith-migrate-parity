#!/usr/bin/env python3
"""fsmig: move legacy feature flags to Flagsmith and prove, per user, that nothing changed.

  inventory  classify legacy flags: supported / not supported (read-only)
  plan       write plan.json (the exact Flagsmith CLI calls) and print its hash (read-only)
  apply      run the plan through the Flagsmith CLI; create-only; needs the plan hash (writes)
  replay     compare legacy vs Flagsmith for N identities, per identity (read-only)
  gate       exit 0 only if a saved replay result proves parity for THIS plan and flags file.
             A precondition for asking a human to approve the switch. It cannot check the human.

Output is deliberately short (token cost). Details go to files. Stdlib only.
Credentials come from the environment, never from arguments:
  FLAGSMITH_API_URL, FLAGSMITH_API_KEY_<host>  (read by the flagsmith CLI)
  FLAGSMITH_ENVIRONMENT_KEY                     (client-side key, used by replay)
"""
import argparse, concurrent.futures as cf, hashlib, json, os, random, re, subprocess, sys, urllib.request

EQ_OPS = {"eq": "EQUAL", "in": "IN"}


def j(o):
    print(json.dumps(o, separators=(",", ":")))


def load(path):
    return json.load(open(path))["flags"]


def trait_name(flag):
    return "legacy_bucket_" + re.sub(r"[^A-Za-z0-9]", "_", flag)


def why_unsupported(f):
    out = []
    for r in f.get("rules", []):
        if r.get("operator", "eq") not in EQ_OPS:
            out.append(f"operator {r.get('operator')!r} on {r.get('attribute')!r}")
    p = f.get("rollout_percent")
    if p is not None and not (isinstance(p, int) and 0 <= p <= 100):
        out.append("rollout_percent is not an integer 0-100")
    if isinstance(f.get("value"), float):
        out.append("float value")
    return out


def vtype(v):
    return "boolean" if isinstance(v, bool) else "integer" if isinstance(v, int) else "string"


def vstr(v):
    return json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else str(v).lower() if isinstance(v, bool) else str(v)


def cmd_inventory(a):
    sup, uns = [], {}
    for f in load(a.flags):
        w = why_unsupported(f)
        (uns.__setitem__(f["name"], w) if w else sup.append(f["name"]))
    j({"supported": sup, "unsupported": uns})


def tree(conds):
    return {"type": "ALL", "conditions": [], "rules": [{"type": "ANY", "conditions": [c], "rules": []} for c in conds]}


def make_plan(flags, mode):
    steps, notes, skipped = [], [], {}
    for f in flags:
        w = why_unsupported(f)
        if w:
            skipped[f["name"]] = w
            continue
        n, v, on = f["name"], f.get("value"), f.get("enabled", True)
        targeted = bool(f.get("rules")) or "rollout_percent" in f
        c = ["feature", "create", n]
        if v is not None:
            c += ["--value", vstr(v)]
        if on and not targeted:
            c.append("--enabled")
        steps.append({"id": "feature:" + n, "cli": c})
        if on and not targeted and isinstance(v, (int, bool)):
            steps.append({"id": "type:" + n, "cli": ["flag", "update", n, "--value", vstr(v), "--type", vtype(v)]})
        if on and targeted:
            conds = [{"property": r["attribute"], "operator": EQ_OPS[r.get("operator", "eq")], "value": str(r["value"])} for r in f.get("rules", [])]
            if "rollout_percent" in f:
                if mode == "preserve":
                    conds.append({"property": trait_name(n), "operator": "LESS_THAN", "value": str(f["rollout_percent"])})
                    notes.append(f"{n}: keeps legacy buckets. The app MUST send trait {trait_name(n)} (legacy bucket 0-99) on every evaluation.")
                else:
                    conds.append({"property": "$.identity.key", "operator": "PERCENTAGE_SPLIT", "value": str(f["rollout_percent"])})
                    notes.append(f"{n}: Flagsmith-native split. Same percentage, DIFFERENT users than legacy.")
            steps.append({"id": "segment:" + n, "cli": ["segment", "create", "mig-" + n, "--rules", json.dumps(tree(conds), separators=(",", ":")), "--feature", n], "capture": "segment_id"})
            ov = ["flag", "update", n, "--enable", "--segment", "{segment_id}"]
            if v is not None:
                ov += ["--value", vstr(v), "--type", vtype(v)]
            steps.append({"id": "override:" + n, "cli": ov})
    return steps, notes, skipped


def plan_hash(mode, steps):
    return hashlib.sha256(json.dumps([mode, steps], sort_keys=True).encode()).hexdigest()[:12]


def cmd_plan(a):
    steps, notes, skipped = make_plan(load(a.flags), a.mode)
    h = plan_hash(a.mode, steps)
    json.dump({"mode": a.mode, "hash": h, "steps": steps, "notes": notes, "skipped": skipped}, open(a.out, "w"), indent=1)
    j({"plan_hash": h, "mode": a.mode, "file": a.out, "creates": [s["id"][8:] for s in steps if s["id"].startswith("feature:")],
       "not_migrated": skipped, "notes": notes, "writes_nothing_yet": True})


def cli(a, *args):
    r = subprocess.run([a.cli, *args, "--project", a.project, "--environment", a.environment, "--yes"], capture_output=True, text=True)
    rc = r.returncode or (1 if r.stdout.lstrip().startswith("Error") or r.stderr.lstrip().startswith("Error") else 0)  # the CLI can print "Error:" and exit 0
    return rc, r.stdout.strip(), (r.stderr + r.stdout).strip()


def cmd_apply(a):
    p = json.load(open(a.plan))
    h = plan_hash(p["mode"], p["steps"])
    if a.approve_hash != h:
        j({"error": "approve-hash does not match this plan; nothing applied", "plan_hash": h})
        return 2
    rc, out, err = cli(a, "feature", "list", "--jq", "[.[].name]")
    if rc:
        j({"error": "cannot read existing features; nothing applied", "detail": err[-200:]})
        return 2
    try:
        have = set(json.loads(out))
    except ValueError:
        j({"error": "unreadable feature list; nothing applied", "detail": out[:200]})
        return 2
    clash = [s["cli"][2] for s in p["steps"] if s["id"].startswith("feature:") and s["cli"][2] in have]
    if clash:
        j({"error": "create-only: these features already exist; nothing applied", "existing": clash})
        return 2
    done, ctx = [], {}
    for s in p["steps"]:
        c = [x.replace("{segment_id}", ctx.get("segment_id", "")) for x in s["cli"]]
        if s.get("capture"):
            c += ["--jq", ".id"]
        rc, out, err = cli(a, *c)
        if rc:
            j({"error": "step failed; stopped", "step": s["id"], "done": done, "detail": err[-300:],
               "state": "partial: features/segments created so far remain in Flagsmith and need manual review"})
            return 1
        if s.get("capture"):
            ctx[s["capture"]] = out.splitlines()[-1].strip()
        done.append(s["id"])
    j({"applied": len(done), "steps": done, "next": "run replay; do not switch the app until parity is shown"})


def server_eval(a, uid, traits):
    body = {"identifier": uid, "traits": [{"trait_key": k, "trait_value": v} for k, v in traits.items()]}
    rq = urllib.request.Request(a.api_url.rstrip("/") + "/api/v1/identities/", json.dumps(body).encode(),
                                {"Content-Type": "application/json", "X-Environment-Key": os.environ["FLAGSMITH_ENVIRONMENT_KEY"]})
    return {f["feature"]["name"]: (f["enabled"], f["feature_state_value"]) for f in json.loads(urllib.request.urlopen(rq, timeout=30).read())["flags"]}


def same_value(old, new):
    if isinstance(old, (dict, list)):
        try:
            return json.loads(new) == old
        except (TypeError, ValueError):
            return False
    return str(old).lower() == str(new).lower()


def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]


def cmd_gate(a):
    why = []
    try:
        r = json.load(open(a.result))
        p = json.load(open(a.plan))
    except (OSError, ValueError) as e:
        j({"gate": "CLOSED", "why": [f"cannot read result or plan: {type(e).__name__}"]})
        return 2
    if r.get("verdict") != "PARITY_ON_SAMPLE":
        why.append(f"last replay verdict is {r.get('verdict')}")
    if r.get("plan_hash") != plan_hash(p["mode"], p["steps"]) or r.get("plan_hash") != p.get("hash"):
        why.append("replay was not run for this plan")
    if r.get("mode") != p["mode"]:
        why.append("replay mode differs from plan mode")
    if r.get("flags_sha") != file_sha(a.flags):
        why.append("legacy flags file changed since the replay")
    if p.get("skipped"):
        why.append("plan leaves flags unmigrated: " + ",".join(p["skipped"]))
    if why:
        j({"gate": "CLOSED", "why": why})
        return 1
    j({"gate": "OPEN_FOR_HUMAN_APPROVAL", "note": "parity on a sample only; a human must still approve switching the app"})


def cmd_replay(a):
    flags = load(a.flags)
    sup = [f for f in flags if not why_unsupported(f)]
    skipped = [f["name"] for f in flags if why_unsupported(f)]
    rng = random.Random(a.seed)
    ids = [{"id": f"user-{i}", "attrs": {"plan": rng.choice(["free", "pro"]), "country": rng.choice(["IN", "US", "DE"])}} for i in range(a.n)]
    r = subprocess.run(a.legacy_cmd, shell=False if isinstance(a.legacy_cmd, list) else True, input="\n".join(map(json.dumps, ids)), capture_output=True, text=True)
    if r.returncode:
        j({"error": "legacy oracle failed", "detail": r.stderr[-200:]})
        return 2
    old = {o["id"]: o for o in map(json.loads, r.stdout.splitlines())}

    def one(q):
        t = dict(q["attrs"])
        if a.mode == "preserve":
            t.update({trait_name(k): v for k, v in old[q["id"]]["buckets"].items()})
        return q["id"], server_eval(a, q["id"], t)

    try:
        with cf.ThreadPoolExecutor(a.threads) as ex:
            new = dict(ex.map(one, ids))
    except Exception as e:  # never print a verdict from a failed run
        j({"error": "replay failed; NO verdict", "detail": f"{type(e).__name__}: {e}"[:200]})
        return 2
    rep, bad_rows = {}, []
    for f in sup:
        n = f["name"]
        c = {"mismatch": 0, "legacy_on": 0, "flagsmith_on": 0, "absent": 0, "value": 0}
        ex_ids = []
        for q in ids:
            o = old[q["id"]]["flags"][n]
            got = new[q["id"]].get(n)
            if got is None:
                c["absent"] += 1; c["mismatch"] += 1; ex_ids.append(q["id"]); continue
            c["legacy_on"] += o["enabled"]; c["flagsmith_on"] += got[0]
            kind = "enabled" if o["enabled"] != got[0] else ("value" if o["enabled"] and o["value"] is not None and not same_value(o["value"], got[1]) else None)
            if kind:
                c["mismatch"] += 1; c["value"] += kind == "value"; ex_ids.append(q["id"]); bad_rows.append([n, q["id"], kind, o["enabled"], got[0]])
        e = {k: v for k, v in c.items() if v or k in ("mismatch", "legacy_on", "flagsmith_on")}
        if c["mismatch"]:
            e["examples"] = ex_ids[:3]
            if "rollout_percent" in f and a.mode == "native":
                e["cause"] = "Flagsmith buckets by its own hash, legacy by its own: same share of users, different users. Use --mode preserve or accept the reshuffle."
            elif c["absent"]:
                e["cause"] = "feature missing from the Flagsmith response"
            else:
                e["cause"] = "unexplained: inspect --details"
        rep[n] = e
    total = sum(v["mismatch"] for v in rep.values())
    verdict = "MISMATCHES" if total else ("PARTIAL_UNMIGRATED_FLAGS" if skipped else "PARITY_ON_SAMPLE")
    if a.details:
        json.dump(bad_rows, open(a.details, "w"))
    if a.result:
        json.dump({"verdict": verdict, "mode": a.mode, "n": a.n, "seed": a.seed, "flags_sha": file_sha(a.flags),
                   "plan_hash": json.load(open(a.plan))["hash"] if a.plan else None, "unmigrated": skipped}, open(a.result, "w"))
    j({"verdict": verdict, "mode": a.mode, "identities": a.n, "seed": a.seed, "flags": rep, "not_migrated": skipped,
       "limits": "sample only. Says nothing about identities, attributes or flags not replayed.",
       "next": "switch the app only after a human approves this result" if verdict != "MISMATCHES" else "do not switch the app"})
    return {"PARITY_ON_SAMPLE": 0, "MISMATCHES": 1}.get(verdict, 3)


def main():
    p = argparse.ArgumentParser(prog="fsmig")
    s = p.add_subparsers(dest="c", required=True)
    x = s.add_parser("inventory"); x.add_argument("--flags", required=True); x.set_defaults(f=cmd_inventory)
    x = s.add_parser("plan"); x.add_argument("--flags", required=True); x.add_argument("--mode", choices=["native", "preserve"], default="preserve"); x.add_argument("--out", default="plan.json"); x.set_defaults(f=cmd_plan)
    x = s.add_parser("apply"); x.add_argument("--plan", required=True); x.add_argument("--approve-hash", required=True)
    x.add_argument("--project", required=True); x.add_argument("--environment", required=True); x.add_argument("--cli", default="flagsmith"); x.set_defaults(f=cmd_apply)
    x = s.add_parser("replay"); x.add_argument("--flags", required=True); x.add_argument("--legacy-cmd", required=True)
    x.add_argument("--mode", choices=["native", "preserve"], default="preserve"); x.add_argument("--n", type=int, default=2000); x.add_argument("--seed", type=int, default=1)
    x.add_argument("--api-url", required=True); x.add_argument("--threads", type=int, default=4); x.add_argument("--details"); x.add_argument("--plan"); x.add_argument("--result"); x.set_defaults(f=cmd_replay)
    x = s.add_parser("gate"); x.add_argument("--flags", required=True); x.add_argument("--plan", required=True); x.add_argument("--result", required=True); x.set_defaults(f=cmd_gate)
    a = p.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
