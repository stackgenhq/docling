#!/bin/sh
set -eu
image=${1:-stackgen-docling:fork-review}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp/manifest.json" <<'PY'
import hashlib
import json
import sys
import tomllib
from pathlib import Path
project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("docling").rglob("*.py")}
manifest = {"distribution": project["name"], "version": project["version"], "files": files}
Path(sys.argv[1]).write_text(json.dumps(manifest), encoding="utf-8")
PY
# Only tests and a digest manifest are mounted. No adapter or SDK source.
docker run --rm --network=none --memory=3g --cpus=2 --entrypoint /opt/app-root/bin/python \
    -v "$PWD/integrations/stackgen_serve/tests:/tests:ro" -v "$tmp:/evidence:ro" \
    "$image" /tests/verify_install.py /evidence/manifest.json
docker run --rm --network=none --memory=3g --cpus=2 --entrypoint /opt/app-root/bin/python \
    -v "$PWD/integrations/stackgen_serve/tests:/tests:ro" "$image" \
    -m unittest discover -s /tests -p 'test_*.py'
for mode in default workers reload; do
    docker run --rm --network=none --memory=3g --cpus=2 --entrypoint /opt/app-root/bin/python \
        -v "$PWD/integrations/stackgen_serve/tests:/tests:ro" "$image" /tests/http_smoke.py "$mode"
done
# Require dependency consistency; never filter pip check output.
docker run --rm --network=none --memory=3g --cpus=2 --entrypoint /opt/app-root/bin/python "$image" -m pip check
