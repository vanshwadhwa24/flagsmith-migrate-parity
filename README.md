# flagsmith-migrate-parity

An agent skill for the Flagsmith CLI. It moves an app's existing feature flags to Flagsmith and checks, user by user, that nobody's experience changed.

Work in progress. Not yet a submission.

## The problem

A 30% rollout moved to Flagsmith is still 30%, but it is not the same 30%. Flagsmith buckets users with its own hash. In local runs on the reference app (800 identities, a 30% rollout), the legacy rule and Flagsmith's native split enabled nearly the same number of users (255 vs 256 in one run, 255 vs 224 in another), but 333 to 349 individual users got a different answer. The exact counts change from project to project because Flagsmith hashes with the segment's id. A check on totals passes. A check per user does not.

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

Token note: SKILL.md plus the tool output of a recorded demo run is about 1,400 tokens by a tokenizer count. That is not a full agent-run total and is not an efficiency claim.

## Layout
`skills/flagsmith-migrate-parity/` the skill and `scripts/fsmig.py`; `examples/legacy-app/` reference legacy flags and replay oracle; `tests/`; `docs/demo-run.txt` a recorded run.
