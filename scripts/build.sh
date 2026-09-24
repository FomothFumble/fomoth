#!/usr/bin/env bash
# Build the C++ core and run its tests.
set -euo pipefail
cd "$(dirname "$0")/.."

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure

echo
echo "core built: build/core/fumble"
echo "python will pick it up automatically (fomoth/native.py)"
