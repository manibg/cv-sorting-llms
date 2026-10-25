"""
Generate a concise Report.pdf (max ~3 pages) for Capstone_Project-CS[02].

Usage:
  python generate_report_pdf.py
"""

from __future__ import annotations

from pathlib import Path


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 90) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if len(trial) <= width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def build_pdf(lines: list[str]) -> bytes:
    """Build a simple multi-page PDF with Helvetica text."""
    page_height = 792
    page_width = 612
    margin_top = 72
    line_height = 14
    max_lines = int((page_height - 2 * margin_top) / line_height)

    pages: list[list[str]] = []
    for i in range(0, len(lines), max_lines):
        pages.append(lines[i : i + max_lines])
    if not pages:
        pages = [[""]]

    objects: list[bytes] = []
    # 1: Catalog, 2: Pages — filled later
    objects.append(b"")  # placeholder index 0 unused
    objects.append(b"")  # 1 catalog
    objects.append(b"")  # 2 pages

    page_obj_ids = []
    content_obj_ids = []

    for page_lines in pages:
        y = page_height - margin_top
        content_parts = ["BT", "/F1 11 Tf", "14 TL", f"50 {y} Td"]
        first = True
        for line in page_lines:
            safe = _escape_pdf_text(line)
            if first:
                content_parts.append(f"({safe}) Tj")
                first = False
            else:
                content_parts.append("T*")
                content_parts.append(f"({safe}) Tj")
        content_parts.append("ET")
        stream = "\n".join(content_parts).encode("latin-1", errors="replace")
        content_id = len(objects)
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        content_obj_ids.append(content_id)

        page_id = len(objects)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {page_id + 1} 0 R >> >> >>"
            ).encode("ascii")
        )
        page_obj_ids.append(page_id)
        # Font object immediately after page
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>".encode("ascii")

    # Assemble PDF
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx in range(1, len(objects)):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(objects[idx])
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for idx in range(1, len(objects)):
        out.extend(f"{offsets[idx]:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def main() -> None:
    paragraphs = [
        "CV Sorting using LLMs (Capstone_Project-CS[02])",
        "Student ID: m0b0xhj",
        "",
        "Abstract",
        "This project implements an automated CV ranking system that scores candidate "
        "resumes against a job description using two free local large language models "
        "(llama3.2 and gemma2) served by Ollama. Resumes in TXT/PDF/DOCX are parsed into "
        "structured text, each model produces an evidence-based fit score with strengths "
        "and gaps, and the scores are aggregated into a transparent ranked list. The "
        "design is modular and plug-and-play: LLM providers, parsers, and ranking logic "
        "are separable. A mock provider enables offline testing of edge cases without a GPU.",
        "",
        "1. Introduction",
        "Recruiters spend significant time manually comparing resumes to role requirements. "
        "Keyword filters miss context, while closed commercial APIs raise cost and privacy "
        "concerns. This capstone builds a terminal-first ranking pipeline using open models "
        "that can run locally.",
        "",
        "2. Problem Statement",
        "Given a job description and a set of candidate CVs, produce a ranked list with "
        "explainable match scores that reflect skills, experience, education, and "
        "responsibility alignment.",
        "",
        "3. Objectives",
        "- Parse CVs and job descriptions from common document formats.",
        "- Use at least two LLMs (llama3.2 + gemma2) with justified dual scoring.",
        "- Aggregate model outputs into a stable ranked list with explanations.",
        "- Keep the codebase simple, testable, and free of LangChain complexity.",
        "- Support plug-and-play LLM backends and offline mock evaluation.",
        "",
        "4. Methodology",
        "Tools: Python 3, Ollama, pypdf, requests. No LangChain.",
        "Workflow: parse JD -> parse CVs -> prompt each LLM -> parse JSON scores -> "
        "weighted aggregate -> rank -> export JSON + console table.",
        "Modules: config.py, parsers.py, prompts.py, llm_client.py (OllamaProvider / "
        "MockLLMProvider), matcher.py, ranker.py, main.py.",
        "Model justification: llama3.2 provides strong general instruction following for "
        "structured JSON scoring; gemma2 adds a second open-weight judgment to reduce "
        "single-model bias. Equal weights (0.5/0.5) keep aggregation interpretable.",
        "",
        "5. Results and Analysis",
        "On the sample corpus (Alice/Bob/Cara vs Senior Python Backend JD), mock dual-model "
        "ranking places Python/backend-aligned profiles above a Java/finance profile. With "
        "--required-skills kubernetes, Cara ranks first due to explicit Kubernetes evidence. "
        "Unit tests cover 40+ cases: empty/corrupt files, invalid LLM JSON, provider "
        "failures, tie-breaking, and skill-filter refinement.",
        "",
        "6. Conclusion",
        "The system meets CS[02] goals with a reliable, free, local dual-LLM ranking "
        "pipeline. Extensions include richer embedding pre-filters, calibrated score "
        "fusion, and optional UI dashboards while preserving the terminal entrypoint.",
    ]

    lines: list[str] = []
    for para in paragraphs:
        if para == "":
            lines.append("")
        elif para.startswith("- "):
            lines.extend(_wrap(para, width=88))
        else:
            lines.extend(_wrap(para, width=88))

    out = Path(__file__).resolve().parents[1] / "Report" / "Report.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_pdf(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
