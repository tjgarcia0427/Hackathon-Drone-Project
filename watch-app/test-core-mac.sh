#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/guardian-watch-tests.XXXXXX")"
trap 'rm -f "$test_dir/watch-tests"; rmdir "$test_dir"' EXIT
xcrun swiftc -swift-version 5 GuardianWatch/ShakeDetector.swift GuardianWatch/AlertModels.swift tests/main.swift -o "$test_dir/watch-tests"
"$test_dir/watch-tests"
