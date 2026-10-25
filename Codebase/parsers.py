"""
Resume and job-description parsers.

Supports .txt, .pdf, and .docx without heavy third-party stacks.
DOCX is read via the OpenXML zip format (stdlib only).
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}

# WordprocessingML namespace used inside .docx files.
_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass
class ParsedDocument:
    """Structured representation of a resume or job description."""

    source_path: str
    raw_text: str
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    experience_years: Optional[float] = None
    education: List[str] = field(default_factory=list)
    summary: str = ""

    def is_empty(self) -> bool:
        """Return True when the document has no usable text."""
        return not (self.raw_text or "").strip()

    def to_prompt_block(self) -> str:
        """Compact text block suitable for LLM prompts."""
        lines = [
            f"Source: {self.source_path}",
            f"Name: {self.candidate_name or 'Unknown'}",
            f"Email: {self.email or 'N/A'}",
            f"Phone: {self.phone or 'N/A'}",
            f"Estimated experience (years): {self.experience_years if self.experience_years is not None else 'N/A'}",
            f"Skills: {', '.join(self.skills) if self.skills else 'N/A'}",
            f"Education: {'; '.join(self.education) if self.education else 'N/A'}",
            "",
            "Full text:",
            self.raw_text.strip(),
        ]
        return "\n".join(lines)


class DocumentParseError(Exception):
    """Raised when a resume/JD cannot be parsed into text."""


def discover_cv_files(cvs_path: str) -> List[Path]:
    """
    Discover CV files from a file or directory path.

    Raises:
        FileNotFoundError: path does not exist
        DocumentParseError: directory has no supported CV files
    """
    path = Path(cvs_path)
    if not path.exists():
        raise FileNotFoundError(f"CVs path not found: {cvs_path}")

    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise DocumentParseError(
                f"Unsupported CV format '{path.suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return [path]

    files = sorted(
        p for p in path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(".")
    )
    if not files:
        raise DocumentParseError(
            f"No supported CV files found in '{cvs_path}'. "
            f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return files


def parse_job_description(jd_path: str) -> ParsedDocument:
    """Parse a job description file into a ParsedDocument."""
    path = Path(jd_path)
    if not path.exists():
        raise FileNotFoundError(f"Job description not found: {jd_path}")
    text = extract_text(path)
    doc = _structure_document(str(path), text, is_job_description=True)
    logger.info("Parsed job description from %s (%d chars)", path, len(text))
    return doc


def parse_cv(cv_path: Path | str) -> ParsedDocument:
    """Parse a single CV file into a ParsedDocument."""
    path = Path(cv_path)
    if not path.exists():
        raise FileNotFoundError(f"CV not found: {cv_path}")
    text = extract_text(path)
    doc = _structure_document(str(path), text, is_job_description=False)
    logger.info("Parsed CV %s (%d chars, skills=%d)", path.name, len(text), len(doc.skills))
    return doc


def extract_text(path: Path) -> str:
    """
    Extract plain text from .txt / .pdf / .docx.

    Raises:
        DocumentParseError: unsupported type or unreadable content
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return _extract_docx(path)
    except DocumentParseError:
        raise
    except Exception as exc:
        logger.error("Failed to extract text from %s: %s", path, exc)
        raise DocumentParseError(f"Failed to read '{path}': {exc}") from exc

    raise DocumentParseError(
        f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def _extract_pdf(path: Path) -> str:
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError(
            "pypdf is required for PDF parsing. Install with: pip install pypdf"
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise DocumentParseError(f"Corrupt or unreadable PDF '{path}': {exc}") from exc

    chunks: List[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as page_exc:
            logger.warning("Skipping unreadable PDF page in %s: %s", path, page_exc)

    text = "\n".join(chunks).strip()
    if not text:
        raise DocumentParseError(f"PDF '{path}' contains no extractable text")
    return text


def _extract_docx(path: Path) -> str:
    """
    Extract text from a .docx by reading word/document.xml inside the zip.
    Avoids a hard dependency on python-docx for easier plug-and-play installs.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise DocumentParseError(f"Invalid DOCX (missing document.xml): {path}")
            xml_bytes = archive.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise DocumentParseError(f"Corrupt DOCX '{path}': {exc}") from exc

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise DocumentParseError(f"Invalid DOCX XML in '{path}': {exc}") from exc

    paragraphs = []
    for para in root.findall(".//w:p", _DOCX_NS):
        texts = [node.text or "" for node in para.findall(".//w:t", _DOCX_NS)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)

    text = "\n".join(paragraphs).strip()
    if not text:
        raise DocumentParseError(f"DOCX '{path}' contains no extractable text")
    return text


def _structure_document(source: str, text: str, is_job_description: bool) -> ParsedDocument:
    """Apply lightweight heuristics to enrich parsed text."""
    cleaned = _normalize_whitespace(text)
    email = _find_email(cleaned)
    phone = _find_phone(cleaned)
    skills = _extract_skills(cleaned)
    experience = _estimate_experience_years(cleaned)
    education = _extract_education(cleaned)
    name = None if is_job_description else _guess_name(cleaned)
    summary = cleaned[:500]

    return ParsedDocument(
        source_path=source,
        raw_text=cleaned,
        candidate_name=name,
        email=email,
        phone=phone,
        skills=skills,
        experience_years=experience,
        education=education,
        summary=summary,
    )


def _normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving line breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_email(text: str) -> Optional[str]:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def _find_phone(text: str) -> Optional[str]:
    match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}", text)
    if not match:
        return None
    candidate = match.group(0).strip()
    digits = re.sub(r"\D", "", candidate)
    return candidate if len(digits) >= 8 else None


def _guess_name(text: str) -> Optional[str]:
    """Use the first non-empty line as a name heuristic when it looks like a person name."""
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or "@" in candidate or len(candidate) > 60:
            continue
        if re.match(r"^[A-Za-z][A-Za-z .'-]{1,58}$", candidate):
            return candidate
        break
    return None


_SKILL_LEXICON = {
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#",
    "sql", "nosql", "mongodb", "postgresql", "mysql", "redis",
    "aws", "azure", "gcp", "docker", "kubernetes", "linux",
    "react", "angular", "vue", "node", "nodejs", "django", "flask", "fastapi", "spring",
    "machine learning", "deep learning", "nlp", "llm", "pytorch", "tensorflow",
    "pandas", "numpy", "spark", "hadoop", "kafka",
    "git", "ci/cd", "rest", "graphql", "microservices", "agile", "scrum",
}


def _extract_skills(text: str) -> List[str]:
    """Extract known skills mentioned in the document (case-insensitive)."""
    lowered = text.lower()
    found = [skill for skill in sorted(_SKILL_LEXICON, key=len, reverse=True) if skill in lowered]
    # Deduplicate while preserving longer phrases first.
    seen = set()
    unique: List[str] = []
    for skill in found:
        if skill not in seen:
            seen.add(skill)
            unique.append(skill)
    return unique


def _estimate_experience_years(text: str) -> Optional[float]:
    """Estimate years of experience from common resume phrases."""
    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)\s+(?:of\s+)?experience",
        r"experience\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _extract_education(text: str) -> List[str]:
    """Collect education-related lines (lightweight heuristic)."""
    keywords = ("bachelor", "master", "b.tech", "m.tech", "b.e", "m.s", "mba", "phd", "bsc", "msc")
    hits = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(k in lowered for k in keywords):
            hits.append(line.strip())
    return hits[:5]
