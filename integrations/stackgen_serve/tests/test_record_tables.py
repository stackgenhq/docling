"""Behavioral regression tests against the runtime-pinned Docling library."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docling_core.transforms.serializer.markdown import (
    MarkdownDocSerializer as UpstreamDocSerializer,
)
from docling_core.types.doc import (
    DoclingDocument,
    RefItem,
    RichTableCell,
    TableCell,
    TableData,
)
from stackgen_docling.install import install


class RecordTableTests(unittest.TestCase):
    """Protect actual cells and export options without allowing a dense grid."""

    @classmethod
    def setUpClass(cls) -> None:
        install()

    def setUp(self) -> None:
        self.grid = patch.object(TableData, "grid", property(self.forbid_grid))
        self.grid.start()
        self.addCleanup(self.grid.stop)

    @staticmethod
    def forbid_grid(_data: TableData) -> None:
        raise AssertionError("Export must never construct TableData.grid")

    def test_actual_coordinates_empty_values_and_special_characters(self) -> None:
        doc = DoclingDocument(name="actual cells")
        cells = [
            TableCell(
                text=text,
                start_row_offset_idx=row,
                end_row_offset_idx=row + 1,
                start_col_offset_idx=col,
                end_col_offset_idx=col + 1,
            )
            for row, col, text in [
                (2, 7, 'line1\n"ü" | <script>&'),
                (0, 0, "Header"),
                (0, 1, ""),
            ]
        ]
        cells[1].column_header = True
        doc.add_table(data=TableData(num_rows=3, num_cols=1881, table_cells=cells))
        output = doc.export_to_markdown()
        self.assertIn('Column 2: ""', output)
        self.assertIn('Column 1 (column header): "Header"', output)
        self.assertNotIn("Record 2", output)
        self.assertNotIn("Column 3:", output)
        values = [
            json.loads(line.split(": ", 1)[1])
            for line in output.splitlines()
            if line.startswith("- Column ")
        ]
        self.assertEqual(values, ["Header", "", cells[0].text])
        self.assertNotIn("<script>", output)

    def test_records_form_one_continuous_block_without_section_or_paragraph_breaks(
        self,
    ) -> None:
        doc = DoclingDocument(name="continuous rows")
        cells = [
            TableCell(
                text=value,
                start_row_offset_idx=row,
                end_row_offset_idx=row + 1,
                start_col_offset_idx=column,
                end_col_offset_idx=column + 1,
            )
            for row, values in enumerate(
                [["Name", "Status"], ["Alice", "Active"], ["Bob", ""]]
            )
            for column, value in enumerate(values)
        ]
        doc.add_table(data=TableData(num_rows=3, num_cols=2, table_cells=cells))
        self.assertEqual(
            doc.export_to_markdown().splitlines(),
            [
                "Table: 3 rows, 2 columns. Only actual cells follow.",
                "Record 1",
                '- Column 1: "Name"',
                '- Column 2: "Status"',
                "Record 2",
                '- Column 1: "Alice"',
                '- Column 2: "Active"',
                "Record 3",
                '- Column 1: "Bob"',
                '- Column 2: ""',
            ],
        )

    def test_merged_cell_written_once_with_span_and_both_header_flags(self) -> None:
        doc = DoclingDocument(name="merged")
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
        output = doc.export_to_markdown()
        self.assertEqual(output.count('"Shared"'), 1)
        self.assertIn("column header; row header; rows 1-2; columns 1-3", output)

    def test_positional_export_arguments_and_non_table_content_stay_upstream(
        self,
    ) -> None:
        from docling_core.types.doc import DocItemLabel

        doc = DoclingDocument(name="options")
        doc.add_text(label=DocItemLabel.TEXT, text="first_text")
        doc.add_text(label=DocItemLabel.TEXT, text="second_text")
        with patch(
            "docling_core.transforms.serializer.markdown.MarkdownDocSerializer",
            UpstreamDocSerializer,
        ):
            expected = doc.export_to_markdown("\n\n", 1, 2, escape_underscores=False)
            sliced = doc.export_to_markdown(to_element=1)
        self.assertEqual(
            doc.export_to_markdown("\n\n", 1, 2, escape_underscores=False), expected
        )
        self.assertEqual(doc.export_to_markdown(to_element=1), sliced)

    def test_callback_character_count_uses_same_exporter(self) -> None:
        from docling_jobkit.convert.results import _build_document_completed_item
        from docling_jobkit.datamodel.exportable_document import ExportableDocument

        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.document import ConversionStatus

        doc = DoclingDocument(name="callback")
        doc.add_table(
            data=TableData(
                num_rows=1,
                num_cols=1881,
                table_cells=[
                    TableCell(
                        text="actual",
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                    )
                ],
            )
        )
        completed = _build_document_completed_item(
            ExportableDocument(
                file=Path("callback.csv"),
                document=doc,
                document_type=InputFormat.CSV,
                status=ConversionStatus.SUCCESS,
            ),
            error=None,
        )
        self.assertEqual(completed.num_characters, len(doc.export_to_markdown()))
        self.assertEqual(completed.num_tables, 1)

    def test_existing_caption_reference_is_preserved(self) -> None:
        from docling_core.types.doc import DocItemLabel

        doc = DoclingDocument(name="caption")
        table = doc.add_table(
            data=TableData(
                num_rows=1,
                num_cols=1,
                table_cells=[
                    TableCell(
                        text="value",
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                    )
                ],
            )
        )
        caption = doc.add_text(label=DocItemLabel.CAPTION, text="Inventory")
        table.captions.append(RefItem(cref=caption.self_ref))
        self.assertIn("Inventory", doc.export_to_markdown())

    def test_layout_caption_below_table_stays_after_table(self) -> None:
        from docling_core.transforms.serializer.markdown import MarkdownParams
        from docling_core.types.doc import (
            BoundingBox,
            CoordOrigin,
            DocItemLabel,
            ProvenanceItem,
        )
        from stackgen_docling.install import RecordMarkdownDocSerializer

        doc = DoclingDocument(name="layout caption")
        caption = doc.add_text(
            label=DocItemLabel.CAPTION,
            text="Below-table caption",
            prov=ProvenanceItem(
                page_no=1,
                charspan=(0, 19),
                bbox=BoundingBox(
                    l=0, t=100, r=100, b=110, coord_origin=CoordOrigin.TOPLEFT
                ),
            ),
        )
        doc.add_table(
            data=TableData(
                num_rows=1,
                num_cols=1,
                table_cells=[
                    TableCell(
                        text="cell",
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                    )
                ],
            ),
            caption=caption,
            prov=ProvenanceItem(
                page_no=1,
                charspan=(0, 4),
                bbox=BoundingBox(
                    l=0, t=0, r=100, b=10, coord_origin=CoordOrigin.TOPLEFT
                ),
            ),
        )
        output = (
            RecordMarkdownDocSerializer(
                doc=doc, params=MarkdownParams(caption_placement="layout")
            )
            .serialize()
            .text
        )
        self.assertLess(
            output.index('Column 1: "cell"'), output.index("Below-table caption")
        )

    def test_native_html_rich_cells_and_multiple_tables(self) -> None:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.html"
            path.write_text(
                "<html><body><h1>Title</h1><table><caption>Inventory</caption>"
                "<tr><th>Name</th><th>Value</th></tr><tr><td>row1</td>"
                "<td><b>blue</b><br/>green</td></tr></table>"
                "<table><tr><td>second table</td></tr></table></body></html>"
            )
            doc = (
                DocumentConverter(allowed_formats=[InputFormat.HTML])
                .convert(path)
                .document
            )
            output = doc.export_to_markdown()
        for token in (
            "Title",
            "Name",
            "Value",
            "row1",
            "blue",
            "green",
            "second table",
        ):
            self.assertIn(token, output)
        self.assertEqual(output.count("Table:"), 2)

    def test_rich_cell_heading_preserves_upstream_cell_text(self) -> None:
        doc = DoclingDocument(name="rich heading")
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
        expected = (
            UpstreamDocSerializer(doc=doc)
            .serialize(item=heading, _nested_in_table=True, in_table_cell=True)
            .text
        )
        output = doc.export_to_markdown()
        value = json.loads(
            next(
                line.split(": ", 1)[1]
                for line in output.splitlines()
                if line.startswith("- Column ")
            )
        )
        self.assertEqual(value, expected)
        self.assertEqual(value, "Heading")

    def test_markdown_export_does_not_change_document_json(self) -> None:
        doc = DoclingDocument(name="unchanged JSON")
        doc.add_table(
            data=TableData(
                num_rows=1,
                num_cols=1881,
                table_cells=[
                    TableCell(
                        text="value",
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                    )
                ],
            )
        )
        # Core's JSON export has its own grid serialization. The no-grid
        # contract applies to Markdown, not to that unchanged upstream path.
        self.grid.stop()
        before = doc.export_to_dict()
        with patch.object(TableData, "grid", property(self.forbid_grid)):
            self.assertIn('Column 1: "value"', doc.export_to_markdown())
        self.assertEqual(doc.export_to_dict(), before)

    def test_unsupported_upstream_version_fails_at_startup(self) -> None:
        with patch("stackgen_docling.install.version", return_value="99.0"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported docling-core"):
                install()

    def test_repeated_install_is_idempotent(self) -> None:
        from docling_core.transforms.serializer import markdown

        original = markdown.MarkdownDocSerializer
        install()
        self.assertIs(markdown.MarkdownDocSerializer, original)


if __name__ == "__main__":
    unittest.main()
