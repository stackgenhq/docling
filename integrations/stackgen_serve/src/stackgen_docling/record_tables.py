"""Render actual table cells without materializing Docling's padded grid."""

import json
from typing import Any

from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    BaseTableSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.transforms.serializer.markdown import (
    MarkdownParams,
    _caption_goes_after,
    _should_use_legacy_annotations,
)
from docling_core.types.doc import DoclingDocument, RichTableCell, TableCell, TableItem


class RecordTableSerializer(BaseTableSerializer):
    """Export existing cells by row; absent positions never become empty objects.

    Parsed cells and output remain in memory. No parser/size-budget changes.
    Span labels retain merged-cell coordinates without duplicating their values.
    """

    def serialize(
        self,
        *,
        item: TableItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        """Preserve upstream captions/options while replacing only table rendering."""
        params = MarkdownParams(**kwargs)
        results = []
        caption = doc_serializer.serialize_captions(item=item, **kwargs)
        caption_after = _caption_goes_after(item, doc, params, standard_after=False)
        if caption.text and not caption_after:
            results.append(caption)
        if item.self_ref not in doc_serializer.get_excluded_refs(**kwargs):
            if _should_use_legacy_annotations(params=params, item=item):
                annotation = doc_serializer.serialize_annotations(item=item, **kwargs)
                if annotation.text:
                    results.append(annotation)
            parts = [
                f"Table: {item.data.num_rows} rows, {item.data.num_cols} columns. "
                "Only actual cells follow.\n"
            ]
            current_row = None
            for cell in sorted(
                item.data.table_cells,
                key=lambda c: (
                    c.start_row_offset_idx,
                    c.start_col_offset_idx,
                ),
            ):
                if cell.start_row_offset_idx != current_row:
                    current_row = cell.start_row_offset_idx
                    parts.append(f"Record {current_row + 1}\n")
                if isinstance(cell, RichTableCell):
                    value = doc_serializer.serialize(
                        item=cell.ref.resolve(doc=doc),
                        **{**kwargs, "_nested_in_table": True, "in_table_cell": True},
                    ).text
                else:
                    value = cell.text
                literal = json.dumps(value, ensure_ascii=False)
                if params.escape_html:
                    for character, escaped in (
                        ("<", r"\u003c"),
                        (">", r"\u003e"),
                        ("&", r"\u0026"),
                    ):
                        literal = literal.replace(character, escaped)
                parts.append(
                    f"- Column {cell.start_col_offset_idx + 1}{self._label(cell)}: {literal}\n"
                )
            results.append(create_ser_result(text="".join(parts), span_source=item))
        if caption.text and caption_after:
            results.append(caption)
        return create_ser_result(
            text="\n\n".join(r.text for r in results), span_source=results
        )

    def _label(self, cell: TableCell) -> str:
        """Keep header flags and merged ranges attached to their actual source cell."""
        labels = []
        if cell.column_header:
            labels.append("column header")
        if cell.row_header:
            labels.append("row header")
        if cell.row_span > 1:
            labels.append(
                f"rows {cell.start_row_offset_idx + 1}-{cell.end_row_offset_idx}"
            )
        if cell.col_span > 1:
            labels.append(
                f"columns {cell.start_col_offset_idx + 1}-{cell.end_col_offset_idx}"
            )
        return f" ({'; '.join(labels)})" if labels else ""
