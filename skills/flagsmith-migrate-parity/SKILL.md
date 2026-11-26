---
name: flagsmith-migrate-parity
description: Migrate an app's existing feature flags to Flagsmith with the Flagsmith CLI without silently changing which users get each feature. Inventories legacy flags, creates features and segments, replays identities against the real Flagsmith server, compares every user, explains each mismatch, and asks a human before the app is switched. Use when moving from a homegrown or other flag system to Flagsmith, or when a percentage rollout must keep the same users.
---

# Flagsmith migration with per-user parity

Why this exists: a 30% rollout moved to Flagsmith still serves about 30%, but not the same users. The totals match, so a count check passes while many individual users flip. This skill compares per user.

Tools: the `flagsmith` CLI (auth by env var, never in arguments) and `scripts/fsmig.py` (stdlib Python). Needs: a legacy flags file, a replay oracle for the legacy code (see below), a Flagsmith project and environment, `FLAGSMITH_API_URL`, `FLAGSMITH_API_KEY_<host>` (master key) and `FLAGSMITH_ENVIRONMENT_KEY` (client-side key).

## Steps

1. Inventory (read-only): `python3 scripts/fsmig.py inventory --flags flags.json`. Anything under `unsupported` is NOT migrated. Say so to the user. Do not approximate it.
2. Pick a mode for rollout flags:
   - `preserve` (default): same users. The app must send the legacy bucket as a trait on every evaluation.
   - `native`: Flagsmith's own split. Same percentage, different users. Only if the user accepts the reshuffle.
3. Plan (read-only): `fsmig.py plan --flags flags.json --mode preserve --out plan.json`. Show the user `plan_hash`, what will be created, what is not migrated, and the notes.
4. Get explicit approval of that plan hash. Then: `fsmig.py apply --plan plan.json --approve-hash <hash> --project <id> --environment <name>`. It creates only; it refuses if any feature already exists or the hash differs. On a failed step it stops and reports the partial state. Do not delete anything unasked.
5. Replay: `fsmig.py replay --flags flags.json --legacy-cmd "<oracle>" --mode <same mode> --api-url <url> --n 2000 --plan plan.json --result result.json`. Exit 0 = parity on the sample, 1 = mismatches, 2 = no verdict (error), 3 = parity but some flags not migrated.
6. Report each mismatch with its `cause`. If the verdict is not `PARITY_ON_SAMPLE`, do not say the migration is done. Offer: fix and replay again, switch to preserve, or stop.
7. Run `fsmig.py gate --flags flags.json --plan plan.json --result result.json`. Exit 0 (OPEN_FOR_HUMAN_APPROVAL) means this exact plan and flags file showed parity on the sample. Exit 1 means CLOSED: do not ask for approval, fix the reasons it lists. The gate cannot check the human. Only after an open gate, ask the user to approve switching the app. Never switch it yourself.

## Oracle
`--legacy-cmd` is a command that reads JSON lines `{"id","attrs"}` on stdin and prints JSON lines `{"id","flags":{name:{"enabled","value"}},"buckets":{name:int}}` using the legacy code itself. `buckets` holds the legacy bucket (0-99) of each rollout flag. See `examples/legacy-app/oracle.py`.

## Tested semantics (reference app, local self-hosted Flagsmith)
Boolean flags, string/int/JSON-as-string values, `eq` and `in` trait rules, percentage rollout (native and preserved), rule plus rollout together, disabled flags, defaults for features that do not exist. Not tested: multivariate values, segment priority, identity overrides, other environments, other operators, Flagsmith Cloud. Parity is shown only for the replayed sample. Not a production migration.

## Keep output small
Every command prints one short JSON line. Use the CLI `--jq` filter when reading state. Details go to files (`--details`).
