#!/usr/bin/env bash
# End-to-end regression against a LOCAL self-hosted Flagsmith (never a real account).
# Needs: a Flagsmith checkout with its API deps (FS_API=/path/to/flagsmith/api, run via `uv`),
# the flagsmith CLI (FS_CLI), and a Postgres reachable by DATABASE_URL (pgserver in our runs).
# Creates fresh empty projects; prints PASS/FAIL per check; exit 1 if any FAIL.
set -u
R=$(cd "$(dirname "$0")/.." && pwd); F=$R/skills/flagsmith-migrate-parity/scripts/fsmig.py
FL=$R/examples/legacy-app/flags.json; OR="python3 $R/examples/legacy-app/oracle.py"
FS_API=${FS_API:-/tmp/fs/api}; FS_CLI=${FS_CLI:-flagsmith}; N=${N:-500}; W=$(mktemp -d); FAILS=0
export EXPERIMENTATION_ENABLED=true DJANGO_SETTINGS_MODULE=app.settings.common SECRET_KEY=localtest DJANGO_ALLOWED_HOSTS='*'
export DATABASE_URL=${DATABASE_URL:-'postgresql://postgres:@/postgres?host=/tmp/pgdata'}
if [ "${START_PG:-1}" = 1 ]; then /tmp/pgv/bin/python -c "import pgserver;pgserver.get_server('/tmp/pgdata',cleanup_mode=None)" >/dev/null 2>&1; fi
(cd "$FS_API" && uv run --python 3.12 --no-dev python manage.py runserver 127.0.0.1:8000 --noreload >"$W/srv.log" 2>&1 &)
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:8000/health/liveness && break; sleep 2; done
sleep 3
check() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1 (got $2, want $3)"; FAILS=$((FAILS+1)); fi; }
newproj() { # $1 = tag. sets PID, exports credentials for that project (secrets stay in $W files)
  (cd "$FS_API" && uv run --python 3.12 --no-dev python "$R/tests/bootstrap_local.py" "$W/$1" 2>>"$W/srv.log" | tail -1 >"$W/$1.json")
  PID=$(jq -r .project "$W/$1.json"); export FLAGSMITH_API_URL=http://127.0.0.1:8000 FLAGSMITH_API_KEY_127_0_0_1_8000=$(cat "$W/$1.token") FLAGSMITH_ENVIRONMENT_KEY=$(cat "$W/$1.envkey"); }
apply() { python3 $F apply --plan "$1" --approve-hash "$2" --project "$PID" --environment dev --cli "$FS_CLI"; }
replay() { python3 $F replay --flags "$FL" --legacy-cmd "$OR" --api-url http://127.0.0.1:8000 --threads 8 --n "$N" "$@"; }
cd "$W"
echo "== A: preserve mode, expect parity and an open gate"
newproj a
H=$(python3 $F plan --flags $FL --mode preserve --out pa.json | jq -r .plan_hash)
check "wrong approval hash applies nothing" "$(apply pa.json 000000000000 >/dev/null; echo $?)" 2
check "apply with right hash" "$(apply pa.json $H >/dev/null; echo $?)" 0
check "re-apply refused (create-only)" "$(apply pa.json $H >/dev/null; echo $?)" 2
replay --mode preserve --plan pa.json --result ra.json >/dev/null; check "preserve replay parity exit" "$?" 0
python3 $F gate --flags $FL --plan pa.json --result ra.json >/dev/null; check "gate open after parity" "$?" 0
echo "== B: sabotage after parity: value changed on the server"
$FS_CLI flag update max-items --value 99 --type integer --project $PID --environment dev --yes >/dev/null
replay --mode preserve --plan pa.json --result rb.json >/dev/null; check "changed value detected (exit 1)" "$?" 1
python3 $F gate --flags $FL --plan pa.json --result rb.json >/dev/null; check "gate closed after mismatch" "$?" 1
echo "== C: native mode, expect rollout mismatches and a closed gate"
newproj c
H=$(python3 $F plan --flags $FL --mode native --out pc.json | jq -r .plan_hash); apply pc.json $H >/dev/null
OUT=$(replay --mode native --plan pc.json --result rc.json); check "native replay mismatch exit" "$?" 1
check "fast-search mismatches > 0" "$(echo "$OUT" | jq '.flags["fast-search"].mismatch>0')" true
check "non-rollout flags still match" "$(echo "$OUT" | jq '.flags["pro-banner"].mismatch')" 0
python3 $F gate --flags $FL --plan pc.json --result rc.json >/dev/null; check "gate closed on native" "$?" 1
echo "== D: unsupported flag is reported, never success"
jq '.flags += [{"name":"email-rule","enabled":true,"rules":[{"attribute":"email","operator":"regex","value":"x"}]}]' $FL > fd.json
newproj d
H=$(python3 $F plan --flags fd.json --mode preserve --out pd.json | jq -r .plan_hash); apply pd.json $H >/dev/null
python3 $F replay --flags fd.json --legacy-cmd "$OR" --api-url http://127.0.0.1:8000 --threads 8 --n "$N" --plan pd.json --result rd.json >/dev/null; check "unmigrated flag exit 3" "$?" 3
python3 $F gate --flags fd.json --plan pd.json --result rd.json >/dev/null; check "gate closed with unmigrated flag" "$?" 1
echo "== E: no verdict when the server is unreachable"
FLAGSMITH_ENVIRONMENT_KEY=bad replay --mode preserve >/dev/null 2>&1; check "bad credentials give exit 2, no verdict" "$?" 2
echo "failures: $FAILS"; exit $((FAILS>0))
