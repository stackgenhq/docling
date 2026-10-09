"""Compare installed fork modules with the checkout manifest, without source mounts."""

import hashlib
import json
import sys
from importlib.metadata import distribution
from pathlib import Path


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    installed = distribution(manifest["distribution"])
    assert installed.version == manifest["version"]
    for relative, expected in manifest["files"].items():
        actual = hashlib.sha256(
            Path(installed.locate_file(relative)).read_bytes()
        ).hexdigest()
        assert actual == expected, relative
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
