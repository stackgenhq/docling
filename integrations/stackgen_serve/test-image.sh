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
# The published image is a flattened copy. WORKDIR may add one empty layer.
# BuildKit does not keep the base in the local image list, so compare the
# recorded runtime from that base.
python3 - "$image" integrations/stackgen_serve/base-runtime.json <<'PY'
import json
import subprocess
import sys
from pathlib import Path

image, runtime_path = sys.argv[1:]
recorded = json.loads(Path(runtime_path).read_text(encoding="utf-8"))
raw = subprocess.check_output(["docker", "image", "inspect", image])
final = json.loads(raw)[0]
layers = final["RootFS"]["Layers"]
if len(layers) > 2:
    raise SystemExit(
        f"{image} has {len(layers)} layers. "
        "The published image must be the flattened copy."
    )
config = final["Config"]
final_env = {}
for item in config["Env"] or []:
    key, value = item.split("=", 1)
    final_env[key] = value
base_env = recorded["env"]
if final_env != base_env:
    missing = sorted(base_env.keys() - final_env.keys())
    extra = sorted(final_env.keys() - base_env.keys())
    changed = sorted(
        key
        for key in final_env.keys() & base_env.keys()
        if final_env[key] != base_env[key]
    )
    raise SystemExit(
        "Environment mismatch. "
        f"Missing {missing}. Extra {extra}. Changed {changed}."
    )
if config["User"] != recorded["user"]:
    raise SystemExit(f"Image user is {config['User']}, expected {recorded['user']}.")
if config["WorkingDir"] != recorded["working_dir"]:
    raise SystemExit(
        f"WorkingDir is {config['WorkingDir']}, expected {recorded['working_dir']}."
    )
if config["Entrypoint"] != ["/opt/app-root/bin/python", "-m", "stackgen_docling"]:
    raise SystemExit(f"Unexpected entrypoint: {config['Entrypoint']}")
if config["Cmd"] != ["run"]:
    raise SystemExit(f"Unexpected command: {config['Cmd']}")
exposed = set((config.get("ExposedPorts") or {}).keys())
expected_ports = set(recorded["exposed_ports"])
if exposed != expected_ports:
    raise SystemExit(f"Exposed ports are {sorted(exposed)}, expected {sorted(expected_ports)}.")
print(json.dumps({"image": image, "layers": len(layers)}))
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
