"""Install the replacement before Serve imports its conversion/export machinery."""

import logging
from importlib.metadata import version

from docling_core.transforms.serializer import markdown
from docling_core.transforms.serializer.base import BaseTableSerializer
from pydantic import Field

from stackgen_docling.record_tables import RecordTableSerializer


class RecordMarkdownDocSerializer(markdown.MarkdownDocSerializer):
    """Keep upstream document serialization; replace its default table strategy."""

    table_serializer: BaseTableSerializer = Field(default_factory=RecordTableSerializer)


def install() -> None:
    """Select record tables for Markdown exports, including callback character counts.

    Document.export_to_markdown imports this class at call time, so the original
    signature/defaults/filtering stay intact. Install once before starting Serve.
    An explicit table_serializer passed by a caller still overrides the default.
    """
    expected = {
        "docling-core": "2.99.0",
        "docling-serve": "1.36.0",
        "docling-jobkit": "3.8.1",
    }
    for distribution, pinned in expected.items():
        installed = version(distribution)
        if installed != pinned:
            raise RuntimeError(
                f"Unsupported {distribution} {installed}; expected {pinned}"
            )
    if markdown.MarkdownDocSerializer is RecordMarkdownDocSerializer:
        return
    markdown.MarkdownDocSerializer = RecordMarkdownDocSerializer
    logging.getLogger(__name__).info("Record-oriented table exporter installed")
