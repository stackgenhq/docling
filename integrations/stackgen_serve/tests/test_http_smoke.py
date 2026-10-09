"""Request-building regressions for the HTTP smoke checks."""

import unittest
from email import policy
from email.parser import BytesParser

from http_smoke import multipart_body


class MultipartBodyTests(unittest.TestCase):
    def test_payload_matching_form_settings_keeps_file_part(self) -> None:
        """Keep file headers intact when CSV values also occur in request settings."""
        boundary = "docling-record-smoke"
        html = b"<html><body><p>Native HTML</p></body></html>"
        for filename, content_type, content in (
            ("records.csv", "text/csv", b"md"),
            ("records.csv", "text/csv", b"md\r\n"),
            ("records.csv", "text/csv", b"placeholder"),
            ("records.html", "text/html", html),
        ):
            with self.subTest(filename=filename, content=content):
                body = multipart_body(
                    boundary,
                    filename=filename,
                    content_type=content_type,
                    content=content,
                )
                message = BytesParser(policy=policy.default).parsebytes(
                    (
                        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
                        "MIME-Version: 1.0\r\n\r\n"
                    ).encode()
                    + body
                )
                parts = list(message.iter_parts())
                fields = {
                    part.get_param("name", header="content-disposition"): part
                    for part in parts
                }
                self.assertEqual(len(parts), 3)
                self.assertEqual(
                    set(fields), {"to_formats", "image_export_mode", "files"}
                )
                self.assertEqual(fields["to_formats"].get_payload(decode=True), b"md")
                self.assertEqual(
                    fields["image_export_mode"].get_payload(decode=True),
                    b"placeholder",
                )
                file = fields["files"]
                self.assertEqual(file.get_filename(), filename)
                self.assertEqual(file.get_content_type(), content_type)
                self.assertEqual(file.get_payload(decode=True), content)
