"""Unit tests for resume / JD parsing edge cases (stdlib unittest)."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from parsers import (
    DocumentParseError,
    discover_cv_files,
    extract_text,
    parse_cv,
    parse_job_description,
)


class ParserTests(unittest.TestCase):
    def test_parse_txt_cv_extracts_contact_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            cv = Path(tmp) / "alice.txt"
            cv.write_text(
                "Alice Johnson\n"
                "alice@example.com\n"
                "+1 555-123-4567\n"
                "5 years of experience with Python, Docker, and AWS.\n"
                "B.Tech Computer Science\n",
                encoding="utf-8",
            )
            doc = parse_cv(cv)
            self.assertEqual(doc.candidate_name, "Alice Johnson")
            self.assertEqual(doc.email, "alice@example.com")
            self.assertIsNotNone(doc.phone)
            self.assertIn("python", doc.skills)
            self.assertEqual(doc.experience_years, 5.0)
            self.assertFalse(doc.is_empty())

    def test_empty_txt_is_empty_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            cv = Path(tmp) / "empty.txt"
            cv.write_text("   \n\n", encoding="utf-8")
            doc = parse_cv(cv)
            self.assertTrue(doc.is_empty())

    def test_discover_cv_files_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("A", encoding="utf-8")
            (root / "b.TXT").write_text("B", encoding="utf-8")
            (root / "ignore.md").write_text("nope", encoding="utf-8")
            files = discover_cv_files(str(root))
            names = {p.name.lower() for p in files}
            self.assertEqual(names, {"a.txt", "b.txt"})

    def test_discover_cv_files_missing_path(self):
        with self.assertRaises(FileNotFoundError):
            discover_cv_files("./does_not_exist_cvs")

    def test_discover_cv_files_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DocumentParseError):
                discover_cv_files(tmp)

    def test_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "resume.png"
            bad.write_bytes(b"not-a-resume")
            with self.assertRaises(DocumentParseError):
                discover_cv_files(str(bad))

    def test_parse_job_description_missing(self):
        with self.assertRaises(FileNotFoundError):
            parse_job_description("./missing_jd.txt")

    def test_docx_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "cv.docx"
            _write_minimal_docx(docx_path, "Bob Smith\nbob@example.com\nSkills: Java, Spring, SQL")
            text = extract_text(docx_path)
            self.assertIn("Bob Smith", text)
            self.assertIn("Java", text)
            doc = parse_cv(docx_path)
            self.assertEqual(doc.email, "bob@example.com")
            self.assertIn("java", doc.skills)

    def test_corrupt_docx_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.docx"
            bad.write_bytes(b"this is not a zip")
            with self.assertRaises(DocumentParseError):
                extract_text(bad)

    def test_corrupt_pdf_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.pdf"
            bad.write_bytes(b"%PDF-1.4 not really a pdf")
            with self.assertRaises(DocumentParseError):
                extract_text(bad)


def _write_minimal_docx(path: Path, text: str) -> None:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in escaped.splitlines()
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)


if __name__ == "__main__":
    unittest.main()
