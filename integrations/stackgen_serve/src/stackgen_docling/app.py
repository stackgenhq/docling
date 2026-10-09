"""Process-local factory used by both direct and spawned Uvicorn servers."""

import logging
import os
from typing import TYPE_CHECKING

from stackgen_docling.install import install

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_app() -> "FastAPI":
    """Install before upstream imports in every worker, including reload children.

    Parent-process module replacements are not inherited by multiprocessing spawn.
    Without this factory, workers silently restore upstream's dense-grid exporter.
    """
    install()
    from docling_serve.app import create_app as upstream_factory

    application = upstream_factory()
    logging.getLogger(__name__).info(
        "Record table factory installed pid=%s", os.getpid()
    )
    return application
