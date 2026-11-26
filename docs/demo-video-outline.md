# Demo video outline (about 3 minutes, draft)

1. 0:00 Problem (20s). "Your rollout says 30%. After migrating, different people have the feature." Show the legacy app flags.json and one user whose answer will flip.
2. 0:20 Skill and CLI (20s). Show SKILL.md steps and that every Flagsmith change goes through the flagsmith CLI.
3. 0:40 Attempt 1, native split (50s). inventory, plan, apply, replay: MISMATCHES, a large share of users differ (345 of 800 in the recorded run; 333 to 349 across runs, varies by project and sample) while totals look equal. Gate CLOSED.
4. 1:30 Attempt 2, preserve (45s). plan notes the trait cost, apply, replay: parity on the sample, gate OPEN FOR HUMAN APPROVAL.
5. 2:15 Safety (30s). Wrong hash applies nothing, re-apply refused, unsupported operator listed as not migrated.
6. 2:45 Limits (15s). Reference app, sample only, not tested: multivariate, priority, overrides. The tool never switches the app.
Recorded from examples/demo.sh. Show real output only.
