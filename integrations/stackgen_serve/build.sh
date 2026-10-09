#!/bin/sh
set -eu
# Run from the repository root. Keep wheel inputs explicit and remove stale wheels.
rm -f integrations/stackgen_serve/dist/*.whl
uv build --wheel --build-constraints integrations/stackgen_serve/build-constraints.txt --out-dir integrations/stackgen_serve/dist
uv build --wheel --build-constraints integrations/stackgen_serve/build-constraints.txt integrations/stackgen_serve --out-dir integrations/stackgen_serve/dist
docker build --network=none -f integrations/stackgen_serve/Dockerfile -t stackgen-docling:fork-review .
