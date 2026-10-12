# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

import json
from io import BytesIO
from unittest.mock import patch

from docling_core.transforms.serializer.markdown import (
    MarkdownDocSerializer,
    MarkdownParams,
)
from docling_core.types.doc import (
    BoundingBox,
    CaptionPlacement,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    RefItem,
    RichTableCell,
    TableCell,
    TableData,
)

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.document_converter import DocumentConverter
from docling.utils.table_records import RecordTableSerializer


def _cell(row: int, column: int, text: str) -> TableCell:
    return TableCell(
        text=text,
        start_row_offset_idx=row,
        end_row_offset_idx=row + 1,
        start_col_offset_idx=column,
        end_col_offset_idx=column + 1,
    )


def _render(doc: DoclingDocument, **kwargs: object) -> str:
    return (
        MarkdownDocSerializer(
            doc=doc,
            table_serializer=RecordTableSerializer(),
            params=MarkdownParams(**kwargs),
        )
        .serialize()
        .text
    )


def test_sparse_cells_keep_coordinates_and_explicit_empty_values() -> None:
    doc = DoclingDocument(name="sparse")
    header = _cell(0, 0, "Header")
    header.column_header = True
    doc.add_table(
        data=TableData(
            num_rows=3,
            num_cols=1881,
            table_cells=[
                _cell(2, 7, 'line1\n"ü" | <script>&'),
                header,
                _cell(0, 1, ""),
            ],
        )
    )
    with patch.object(
        TableData,
        "grid",
        property(lambda _: (_ for _ in ()).throw(AssertionError("grid accessed"))),
    ):
        actual = _render(doc)
    assert actual.splitlines() == [
        "Table: 3 rows, 1881 columns. Only actual cells follow.",
        "Record 1",
        '- Column 1 (column header): "Header"',
        '- Column 2: ""',
        "Record 3",
        '- Column 8: "line1\\n\\"ü\\" | \\u003cscript\\u003e\\u0026"',
    ]
    assert (
        json.loads(actual.splitlines()[-1].split(": ", 1)[1])
        == 'line1\n"ü" | <script>&'
    )


def test_csv_conversion_keeps_document_cells_and_changes_only_selected_export() -> None:
    source = b"Name,Status,Note\nAda,,ready\nLin,active,\n"
    result = DocumentConverter(allowed_formats=[InputFormat.CSV]).convert(
        DocumentStream(name="records.csv", stream=BytesIO(source))
    )
    doc = result.document
    table = doc.tables[0]
    expected = [cell.text for cell in table.data.table_cells]
    assert expected == [
        "Name",
        "Status",
        "Note",
        "Ada",
        "",
        "ready",
        "Lin",
        "active",
        "",
    ]
    assert [
        (cell.start_row_offset_idx, cell.start_col_offset_idx)
        for cell in table.data.table_cells
    ] == [(row, column) for row in range(3) for column in range(3)]
    output = _render(doc)
    values = [
        json.loads(line.split(": ", 1)[1])
        for line in output.splitlines()
        if line.startswith("- Column ")
    ]
    assert values == expected
    assert doc.export_to_markdown().startswith("| Name")


def test_spans_and_header_flags_are_attached_to_origin_cell() -> None:
    doc = DoclingDocument(name="spans")
    doc.add_table(
        data=TableData(
            num_rows=2,
            num_cols=3,
            table_cells=[
                TableCell(
                    text="Shared",
                    row_span=2,
                    col_span=3,
                    column_header=True,
                    row_header=True,
                    start_row_offset_idx=0,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=3,
                )
            ],
        )
    )
    assert _render(doc).splitlines()[-1] == (
        '- Column 1 (column header; row header; rows 1-2; columns 1-3): "Shared"'
    )


def test_record_serializer_is_opt_in_and_does_not_change_json() -> None:
    doc = DoclingDocument(name="default")
    doc.add_table(
        data=TableData(num_rows=1, num_cols=2, table_cells=[_cell(0, 0, "A")])
    )
    before = doc.export_to_dict()
    original = doc.export_to_markdown()
    assert "|" in original
    assert "Record 1" not in original
    assert 'Column 1: "A"' in _render(doc)
    assert doc.export_to_markdown() == original
    assert doc.export_to_dict() == before


def test_rich_cells_and_nested_tables_are_serialized_once_without_grid() -> None:
    doc = DoclingDocument(name="nested")
    outer = doc.add_table(data=TableData(num_rows=1, num_cols=2, table_cells=[]))
    inner = doc.add_table(
        parent=outer,
        data=TableData(
            num_rows=1, num_cols=1, table_cells=[_cell(0, 0, "nested value")]
        ),
    )
    outer.data.table_cells.extend(
        [
            RichTableCell(
                text="",
                ref=RefItem(cref=inner.self_ref),
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=0,
                end_col_offset_idx=1,
            ),
            _cell(0, 1, "after"),
        ]
    )
    with patch.object(
        TableData,
        "grid",
        property(lambda _: (_ for _ in ()).throw(AssertionError("grid accessed"))),
    ):
        result = _render(doc)
    assert result.count("nested value") == 1
    assert 'Column 1: "nested value"' in result
    assert 'Column 2: "after"' in result
    assert result.count("Table:") == 1


def test_rich_heading_and_caption_keep_their_document_spans() -> None:
    doc = DoclingDocument(name="rich")
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[]))
    heading = doc.add_heading(text="Heading", level=1, parent=table)
    table.data.table_cells.append(
        RichTableCell(
            text="",
            ref=RefItem(cref=heading.self_ref),
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
        )
    )
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Inventory")
    table.captions.append(RefItem(cref=caption.self_ref))
    result = MarkdownDocSerializer(
        doc=doc, table_serializer=RecordTableSerializer()
    ).serialize()
    assert 'Column 1: "Heading"' in result.text
    assert result.text.startswith("Inventory\n\nTable:")
    assert {item.self_ref for item in result.get_unique_doc_items()} >= {
        table.self_ref,
        caption.self_ref,
    }


def test_layout_caption_below_table_follows_records() -> None:
    doc = DoclingDocument(name="layout")
    caption = doc.add_text(
        label=DocItemLabel.CAPTION,
        text="Below table",
        prov=ProvenanceItem(
            page_no=1,
            charspan=(0, 11),
            bbox=BoundingBox(
                l=0, t=100, r=100, b=110, coord_origin=CoordOrigin.TOPLEFT
            ),
        ),
    )
    doc.add_table(
        data=TableData(num_rows=1, num_cols=1, table_cells=[_cell(0, 0, "value")]),
        caption=caption,
        prov=ProvenanceItem(
            page_no=1,
            charspan=(0, 5),
            bbox=BoundingBox(l=0, t=0, r=100, b=10, coord_origin=CoordOrigin.TOPLEFT),
        ),
    )
    output = _render(doc, caption_placement=CaptionPlacement.LAYOUT)
    assert output.index('Column 1: "value"') < output.index("Below table")
