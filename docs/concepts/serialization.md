## Introduction

A *document serializer* (AKA simply *serializer*) is a Docling abstraction that is
initialized with a given [`DoclingDocument`](./docling_document.md) and returns a
textual representation for that document.

Besides the document serializer, Docling defines similar abstractions for several
document subcomponents, for example: *text serializer*, *table serializer*,
*picture serializer*, *list serializer*, *inline serializer*, and more.

Last but not least, a *serializer provider* is a wrapper that abstracts the
document serialization strategy from the document instance.

## Base classes

To enable both flexibility for downstream applications and out-of-the-box utility,
Docling defines a serialization class hierarchy, providing:

- base types for the above abstractions: `BaseDocSerializer`, as well as
  `BaseTextSerializer`, `BaseTableSerializer` etc, and `BaseSerializerProvider`, and
- specific subclasses for the above-mentioned base types, e.g. `MarkdownDocSerializer`.

You can review all methods required to define the above base classes [here](https://github.com/docling-project/docling-core/blob/main/docling_core/transforms/serializer/base.py).

From a client perspective, the most relevant is `BaseDocSerializer.serialize()`, which
returns the textual representation, as well as relevant metadata on which document
components contributed to that serialization.

## Use in `DoclingDocument` export methods

Docling provides predefined serializers for Markdown, HTML, and DocTags.

The respective `DoclingDocument` export methods (e.g. `export_to_markdown()`) are
provided as user shorthands — internally directly instantiating and delegating to
respective serializers.

## Format-specific behaviors

Each serializer makes format-specific trade-offs when representing document
features that have no direct equivalent in the target format. The most notable
case is **table cell spanning** (rowspan / colspan).

### Table cell spans

Docling's internal table model (`TableData.grid`) preserves full span metadata
for every cell - `row_span`, `col_span`, `start_row_offset_idx`, and
`start_col_offset_idx`. How that metadata is rendered depends on the output
format:

| Format | Span handling |
|----------|---------------|
| JSON | Preserved. The full `TableData` model is serialized losslessly, including all span fields. |
| Doclang | Preserved. Tables are serialized via OTSL with explicit continuation tokens (`LCEL` for colspan, `UCEL` for rowspan, `XCEL` for both). |
| DocTags | Preserved. Tables are serialized via OTSL, which natively encodes span structure. |
| HTML | Preserved. Cells are emitted with native `rowspan` / `colspan` attributes. |
| Markdown | **Flattened.** Markdown tables have no span syntax, so the serializer writes cell text at the origin position only; all other grid positions covered by the span are rendered as empty cells. |
| LaTeX | **Flattened.** The `tabular` environment is emitted without `\multirow` / `\multicolumn` commands for now. |
| WebVTT | **Not applicable.** Tables are not serialized (WebVTT is a subtitle/caption format). |


If your downstream workflow depends on accurate table structure (e.g. merged
header cells), prefer `export_to_html()` or `export_to_dict()` over
`export_to_markdown()`. Alternatively, you can override the default table
serializer for any format by subclassing `BaseTableSerializer` and passing your
implementation when instantiating the document serializer.


## Record-oriented table text

For wide, sparse tables, you can opt in to a record-oriented table serializer.
It writes each source cell once, with its one-based row and column position.
It does not build the padded `TableData.grid` during table rendering.

From Python, select the record format for one export:

```python
from docling.document_converter import DocumentConverter
from docling.utils.table_records import export_to_record_markdown

doc = DocumentConverter().convert("input.pdf").document
text = export_to_record_markdown(doc)
```

Use `save_as_record_markdown(doc, "output.md", image_mode=ImageRefMode.REFERENCED)`
if you need a file and referenced images. For other Markdown settings, pass
`params=MarkdownParams(...)` to `export_to_record_markdown`. You can also
select `RecordTableSerializer()` directly on a `MarkdownDocSerializer` instance.
The `DoclingDocument` Markdown methods belong to `docling-core` and do not
accept a table serializer.

From the CLI, use `--markdown-table-format records` on `docling convert` (or
`docling convert-remote` when writing the returned document locally):

```bash
docling convert input.csv --from csv --to md --markdown-table-format records --output ./out
```

The default is `--markdown-table-format default`. The option changes only
Markdown output. Other formats remain unchanged. `convert-remote` applies the
setting in the local exporter; it does not send the setting to Docling Serve.

This is text within a Markdown export, **not** a Markdown pipe table. Missing
positions are omitted, but explicit empty cells are present. Header flags and
merged ranges are written beside their source cells. `RichTableCell` content is
flattened to text; use `export_to_dict()` if you need the full document structure.
The default `export_to_markdown()` output does not change. Conversion and the
final output string still use memory, so this option is not a general memory
limit for large documents.

## Examples

For an example showcasing how to use serializers, see
[here](../examples/serialization.ipynb).
