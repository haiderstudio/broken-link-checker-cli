#!/bin/sh
# Check the bundled examples. Run from the repo root:
#   sh examples/run-example.sh
# Expected: 2 ok, 1 broken (missing-page.md), exit code 1.
set +e
cd "$(dirname "$0")/.."
python3 src/broken_link_checker.py examples/
