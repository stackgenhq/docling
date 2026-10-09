"""Preserve Serve's CLI while directing every server process to our factory."""

import importlib
from typing import Any
from unittest.mock import patch

import uvicorn

from stackgen_docling.install import install


class _ServerRunner:
    """Redirect the pinned CLI's factory without patching the shared Uvicorn module."""

    def run(self, *, app: str, **kwargs: Any) -> None:
        """Keep upstream options, but install inside spawned workers/reload children."""
        uvicorn.run(app="stackgen_docling.app:create_app", **kwargs)


def main() -> None:
    """Install for CLI work; delegate serving-process installation to our factory."""
    install()
    upstream = importlib.import_module("docling_serve.__main__")
    with patch.object(upstream, "uvicorn", _ServerRunner()):
        upstream.app()


if __name__ == "__main__":
    main()
