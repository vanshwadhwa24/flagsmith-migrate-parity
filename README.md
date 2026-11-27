# flagsmith-migrate-parity

An agent skill for the Flagsmith CLI. It moves an app's existing feature flags to Flagsmith and checks, user by user, that nobody's experience changed.

## The problem

A 30% rollout moved to Flagsmith is still 30%, but it is not the same 30%. Flagsmith buckets users with its own hash. In the run shown in the demo video on the reference app (500 identities, two percentage-split flags, Flagsmith-native mode), the legacy rule and Flagsmith enabled nearly the same number of users (fast-search: 162 vs 133, pro-beta: 116 vs 127), but 215 and 125 individual users got a different answer. Exact counts change from project to project because Flagsmith hashes with the segment's id. A check on totals passes. A check per user does not. In preserve mode the same run had 0 mismatches on the 500-identity sample.

## What the skill does

1. `inventory`: lists which legacy flags it can migrate. Anything else is reported as not migrated.
2. `plan`: writes the exact Flagsmith CLI calls and a plan hash. Nothing is created yet.
3. `apply`: runs the plan through the Flagsmith CLI only if the human-approved hash matches. Create-only: it refuses if a feature already exists.
4. `replay`: sends N identities through the legacy code and the real Flagsmith server and compares every user. Each mismatch gets a cause.
5. `gate`: opens only if the saved replay shows parity for this exact plan and flags file.

Rollout modes: `preserve` keeps the same users by sending the legacy bucket (0-99) as a trait and using a `LESS_THAN` rule. The cost: the app must compute and send that trait on every evaluation. `native` uses Flagsmith's split and reshuffles users.

## Safety boundary before switching the app

Enforced in code: apply needs the matching plan hash; apply never touches existing features; a failed or unreadable replay gives "no verdict" and a non-zero exit; unmigrated flags can never produce a plain success; the gate is closed unless a replay of this plan and this flags file shows parity.

Not enforced in code: that a human approved. The tool cannot tell a person from an agent typing a hash. The skill text tells the agent to ask a person after the gate opens and never to switch the app itself. This tool also does not switch your app or touch production data. It does not delete anything on failure.

## Tested (local self-hosted Flagsmith, reference app in `examples/legacy-app`)
- `python3 -m unittest tests/test_unit.py`: 9 offline tests.
- `bash tests/e2e_local.sh`: 14 checks against a local Flagsmith and fresh empty projects: parity in preserve mode, detection of a changed value, native-mode mismatches, unmigrated flags, create-only, wrong hash, closed gate, bad credentials.
- Flags covered: boolean, string/int/JSON-as-string values, `eq` and `in` trait rules, percentage rollout, rule plus rollout, disabled flags.

## Not tested / limits
Multivariate flags, segment priority, identity overrides, multiple environments, operators other than `eq` and `in`, Flagsmith Cloud, other legacy systems. Parity is shown only for the sampled identities and attributes. This is not a production migration. The reference legacy app is ours, not a real vendor's.

Token note: SKILL.md plus the tool output of a recorded demo run is about 1,700 tokens (SKILL.md 900 + demo output 821, counted with tiktoken cl100k_base on the files in this repo). That is not a full agent-run total and is not an efficiency claim.

## Run the tests

Unit tests need only Python 3: `python3 -m unittest tests/test_unit.py`.

The end-to-end test and demo run against a local, throwaway Flagsmith. They never touch a real account. You need:
- a checkout of https://github.com/Flagsmith/flagsmith with its API dependencies installable by `uv` (Python 3.12),
- the Flagsmith CLI (`npm install -g @flagsmith/cli`, or set `FS_CLI` to its path),
- `jq`, `curl`, `python3`,
- an empty throwaway Postgres database, for example `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pw postgres:16`.

```
export FS_API=/path/to/flagsmith/api
export DATABASE_URL=postgresql://postgres:pw@127.0.0.1:5432/postgres
export FS_CLI=flagsmith            # or the full path to the CLI
bash tests/e2e_local.sh            # 14 checks, prints PASS/FAIL
bash examples/demo.sh              # native vs preserve narrative
```

The scripts start the Flagsmith dev server on 127.0.0.1:8000 and create fresh empty projects. They apply database migrations first (first run takes a few minutes). They leave the server running; stop it afterwards.

## Layout
`skills/flagsmith-migrate-parity/` the skill and `scripts/fsmig.py`; `examples/legacy-app/` reference legacy flags and replay oracle; `tests/`; `docs/demo-run.txt` a recorded run.
