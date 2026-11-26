#!/usr/bin/env bash
# Demo narrative on a LOCAL Flagsmith: native migration fails per-user, preserve migration passes, gate shows both.
# Same prerequisites as tests/e2e_local.sh (README, section "Run the tests").
set -u
R=$(cd "$(dirname "$0")/.." && pwd); F=$R/skills/flagsmith-migrate-parity/scripts/fsmig.py
FL=$R/examples/legacy-app/flags.json; OR="python3 $R/examples/legacy-app/oracle.py"
FS_API=${FS_API:?set FS_API to the api/ directory of a local Flagsmith checkout (see README)}; FS_CLI=${FS_CLI:-flagsmith}; N=${N:-500}; W=$(mktemp -d); FAILS=0
export EXPERIMENTATION_ENABLED=true DJANGO_SETTINGS_MODULE=app.settings.common SECRET_KEY=localtest DJANGO_ALLOWED_HOSTS='*'
export DATABASE_URL=${DATABASE_URL:?set DATABASE_URL to a throwaway local Postgres (see README)}
(cd "$FS_API" && uv run --python 3.12 --no-dev python manage.py migrate --noinput >"$W/migrate.log" 2>&1) || { echo "migrate failed, see $W/migrate.log"; exit 2; }
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
say() { echo; echo "\$ $*"; }
cp $FL legacy.json
say "fsmig inventory"; python3 $F inventory --flags legacy.json
echo; echo "### Attempt 1: Flagsmith-native percentage split"
newproj n; say "fsmig plan --mode native"; H=$(python3 $F plan --flags legacy.json --mode native --out pn.json | tee /dev/stderr | jq -r .plan_hash) 2>&1
say "fsmig apply --approve-hash $H"; apply pn.json $H
say "fsmig replay --mode native"; replay --mode native --plan pn.json --result rn.json | jq -c '{verdict,mode,identities,fast_search:.flags["fast-search"],pro_beta:.flags["pro-beta"],other_flags_mismatch:([.flags|to_entries[]|select(.key!="fast-search" and .key!="pro-beta")|.value.mismatch]|add)}'
say "fsmig gate"; python3 $F gate --flags legacy.json --plan pn.json --result rn.json
echo; echo "### Attempt 2: preserve the legacy buckets"
newproj p; say "fsmig plan --mode preserve"; H=$(python3 $F plan --flags legacy.json --mode preserve --out pp.json | tee /dev/stderr | jq -r .plan_hash) 2>&1
say "fsmig apply --approve-hash $H"; apply pp.json $H
say "fsmig replay --mode preserve"; replay --mode preserve --plan pp.json --result rp.json | jq -c '{verdict,mode,identities,total_mismatches:([.flags[]|.mismatch]|add)}'
say "fsmig gate"; python3 $F gate --flags legacy.json --plan pp.json --result rp.json
echo; echo "(a human is now asked to approve switching the app; the tool never switches it)"
