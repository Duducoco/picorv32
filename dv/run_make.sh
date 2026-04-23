#!/usr/bin/env bash
# Run random verification for every test in testlist.yaml against PicoRV32.
# Runs up to half the system CPU cores in parallel; each (test, seed) pair
# gets its own output dir out/picorv32/{test}_{seed}/ and collects coverage.
# Usage: ./run_make.sh [TEST_NUM]
#   TEST_NUM: number of random-seed runs per test (default: 3)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTLIST="$SCRIPT_DIR/cfg/testlist.yaml"
TEST_NUM="${1:-50}"

MAX_JOBS=$(( $(nproc) / 2 ))
(( MAX_JOBS < 1 )) && MAX_JOBS=1

RESULT_DIR=$(mktemp -d)
trap 'rm -rf "$RESULT_DIR"' EXIT

mapfile -t TESTS < <(grep '^- test:' "$TESTLIST" | awk '{print $3}' | tr -d '\r')
[[ ${#TESTS[@]} -eq 0 ]] && { echo "ERROR: No tests found in $TESTLIST"; exit 1; }

total=$(( ${#TESTS[@]} * TEST_NUM ))

echo "============================================================"
echo " PicoRV32 random verification"
echo " Tests: ${#TESTS[@]}, Runs/test: $TEST_NUM, Total: $total"
echo " Parallel jobs: $MAX_JOBS / $(nproc) CPUs"
echo "============================================================"

run_one() {
    local test="$1" seed="$2"

    make -C "$SCRIPT_DIR" riscv_dv_test TEST="$test" SEED="$seed" \
        > "$RESULT_DIR/${test}__${seed}.log" 2>&1
    local rc=$?

    local status
    if (( rc != 0 )); then
        status="ERROR(make)"
    elif grep -q "\[PASS\]" "$RESULT_DIR/${test}__${seed}.log" 2>/dev/null; then
        status="PASS"
    else
        status="FAIL"
    fi

    echo "$status" > "$RESULT_DIR/${test}__${seed}.result"
    echo "[$status] $test  seed=$seed"
}

declare -a pids=()

for test in "${TESTS[@]}"; do
    for ((i = 0; i < TEST_NUM; i++)); do
        seed=$RANDOM

        # Throttle: wait for a slot to open
        while (( ${#pids[@]} >= MAX_JOBS )); do
            wait -n 2>/dev/null || true
            new_pids=()
            for pid in "${pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && new_pids+=("$pid")
            done
            pids=("${new_pids[@]}")
        done

        echo "  --> launching $test  seed=$seed"
        run_one "$test" "$seed" &
        pids+=($!)
    done
done

wait  # drain remaining jobs

# Collect and print results
echo ""
echo "============================================================"
echo " RESULTS:"
pass=0; fail=0
declare -a results=()
for f in "$RESULT_DIR"/*.result; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f" .result)
    test="${base%__*}"
    seed="${base##*__}"
    status=$(<"$f")
    results+=("[$status] $test  seed=$seed")
    if [[ $status == "PASS" ]]; then (( ++pass )); else (( ++fail )); fi
done

printf '%s\n' "${results[@]}" | sort | sed 's/^/  /'

echo ""
echo " SUMMARY: $pass/$total PASSED,  $fail FAILED"
echo "============================================================"

(( fail == 0 ))
