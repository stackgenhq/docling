"""Compare installed fork modules with the checkout manifest, without source mounts."""

import hashlib
import json
import shutil
import sys
from importlib.metadata import distribution
from importlib.util import find_spec
from pathlib import Path


def check_xray_blockers() -> None:
    """Fail if the image again ships rsync or the testing_utils bytecode with example keys."""
    assert shutil.which("rsync") is None, "rsync is installed"
    spec = find_spec("transformers")
    assert spec is not None and spec.submodule_search_locations
    for location in spec.submodule_search_locations:
        leaked = sorted(Path(location).glob("__pycache__/testing_utils*.pyc"))
        assert not leaked, leaked


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    installed = distribution(manifest["distribution"])
    assert installed.version == manifest["version"]
    for relative, expected in manifest["files"].items():
        actual = hashlib.sha256(
            Path(installed.locate_file(relative)).read_bytes()
        ).hexdigest()
        assert actual == expected, relative
    check_xray_blockers()
    print(
        json.dumps(
            {
                "distribution": manifest["distribution"],
                "version": installed.version,
                "verified_files": len(manifest["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()
