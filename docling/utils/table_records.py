# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT
"""Render table cells as labeled records without building a padded grid."""

import json
from typing import Any

from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    BaseTableSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.transforms.serializer.markdown import MarkdownParams
from docling_core.types.doc import (
    CaptionPlacement,
    CoordOrigin,
    DoclingDocument,
    NodeItem,
    ProvenanceItem,
    RichTableCell,
    TableCell,
    TableItem,
    TextItem,
)


class RecordTableSerializer(BaseTableSerializer):
    """Write one entry per source cell, including its position and span.

    Missing positions are omitted; explicit empty cells are not. The output is
    text in a Markdown document, not a Markdown pipe table. Select this class
    on a ``MarkdownDocSerializer`` instance to leave other exports unchanged.
    """

    def serialize(
        self,
        *,
        item: TableItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        if kwargs.get("_nested_in_table"):
            visited = kwargs.get("visited")
            if isinstance(visited, set):
                _mark_visited(item, doc, visited)
            return create_ser_result(
                text=_nested_text(
                    item, doc, doc_serializer.get_excluded_refs(**kwargs)
                ),
                span_source=item,
            )

        params = MarkdownParams(**kwargs)
        caption = doc_serializer.serialize_captions(item=item, **kwargs)
        caption_after = _caption_after(item, doc, params)
        parts: list[SerializationResult] = []
        if caption.text and not caption_after:
            parts.append(caption)

        if item.self_ref not in doc_serializer.get_excluded_refs(**kwargs):
            lines = [
                f"Table: {item.data.num_rows} rows, {item.data.num_cols} columns. "
                "Only actual cells follow.\n"
            ]
            current_row = -1
            for cell in sorted(
                item.data.table_cells,
                key=lambda cell: (cell.start_row_offset_idx, cell.start_col_offset_idx),
            ):
                if cell.start_row_offset_idx != current_row:
                    current_row = cell.start_row_offset_idx
                    lines.append(f"Record {current_row + 1}\n")
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
                lines.append(
                    f"- Column {cell.start_col_offset_idx + 1}{_cell_label(cell)}: {literal}\n"
                )
            parts.append(
                create_ser_result(text="".join(lines).rstrip(), span_source=item)
            )

        if caption.text and caption_after:
            parts.append(caption)
        return create_ser_result(
            text="\n\n".join(part.text for part in parts if part.text),
            span_source=parts,
        )


def _cell_label(cell: TableCell) -> str:
    labels = []
    if cell.column_header:
        labels.append("column header")
    if cell.row_header:
        labels.append("row header")
    if cell.row_span > 1:
        labels.append(f"rows {cell.start_row_offset_idx + 1}-{cell.end_row_offset_idx}")
    if cell.col_span > 1:
        labels.append(
            f"columns {cell.start_col_offset_idx + 1}-{cell.end_col_offset_idx}"
        )
    return f" ({'; '.join(labels)})" if labels else ""


def _mark_visited(item: NodeItem, doc: DoclingDocument, visited: set[str]) -> None:
    visited.add(item.self_ref)
    for child in item.children:
        _mark_visited(child.resolve(doc=doc), doc, visited)


def _nested_text(item: NodeItem, doc: DoclingDocument, excluded: set[str]) -> str:
    if item.self_ref in excluded:
        return ""
    if isinstance(item, TableItem):
        values = []
        for cell in sorted(
            item.data.table_cells,
            key=lambda cell: (cell.start_row_offset_idx, cell.start_col_offset_idx),
        ):
            value = (
                _nested_text(cell.ref.resolve(doc=doc), doc, excluded)
                if isinstance(cell, RichTableCell)
                else cell.text
            )
            if value:
                values.append(value)
        return " ".join(values)
    values = [item.text] if isinstance(item, TextItem) and item.text else []
    for child in item.children:
        text = _nested_text(child.resolve(doc=doc), doc, excluded)
        if text:
            values.append(text)
    return " ".join(values)


def _caption_after(
    item: TableItem, doc: DoclingDocument, params: MarkdownParams
) -> bool:
    if (
        params.caption_placement != CaptionPlacement.LAYOUT
        or not item.prov
        or not item.captions
    ):
        return False
    table_prov = item.prov[0]
    table_y = _center_y(table_prov, doc)
    if table_y is None:
        return False
    for caption_ref in item.captions:
        caption = caption_ref.resolve(doc=doc)
        if not isinstance(caption, TextItem):
            return False
        caption_prov = next(
            (prov for prov in caption.prov if prov.page_no == table_prov.page_no),
            None,
        )
        if caption_prov is None or (caption_y := _center_y(caption_prov, doc)) is None:
            return False
        if caption_y <= table_y:
            return False
    return True


def _center_y(prov: ProvenanceItem, doc: DoclingDocument) -> float | None:
    bbox = prov.bbox
    if bbox.coord_origin != CoordOrigin.TOPLEFT:
        page = doc.pages.get(prov.page_no)
        if page is None:
            return None
        bbox = bbox.to_top_left_origin(page_height=page.size.height)
    return (bbox.t + bbox.b) / 2
