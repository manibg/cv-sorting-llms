"""
Prompt templates for JD parsing and candidate–job matching.

Kept as plain functions (no LangChain) so prompts are easy to read and swap.
"""

from __future__ import annotations

from parsers import ParsedDocument


MATCH_SYSTEM_PROMPT = (
    "You are an expert technical recruiter. Score how well a candidate resume "
    "matches a job description. Be strict, fair, and evidence-based. "
    "Respond with ONLY valid JSON. No markdown fences."
)


def build_match_prompt(resume: ParsedDocument, job: ParsedDocument, required_skills: list[str] | None = None) -> str:
    """
    Build the user prompt that asks an LLM to score one resume against one JD.

    The model must return JSON with overall_score (0-100), requirement scores,
    strengths, gaps, and a short explanation.
    """
    skills_filter = ""
    if required_skills:
        skills_filter = (
            "\nAdditional hard filters (penalize heavily if missing): "
            + ", ".join(required_skills)
        )

    return f"""Score this candidate against the job description.

JOB DESCRIPTION:
{job.to_prompt_block()}
{skills_filter}

CANDIDATE RESUME:
{resume.to_prompt_block()}

Return ONLY a JSON object with this exact schema:
{{
  "overall_score": <number 0-100>,
  "requirement_scores": {{
    "skills_match": <number 0-100>,
    "experience_match": <number 0-100>,
    "education_match": <number 0-100>,
    "responsibilities_match": <number 0-100>
  }},
  "strengths": ["short bullet", "..."],
  "gaps": ["short bullet", "..."],
  "explanation": "2-4 sentences citing concrete evidence from the resume"
}}
"""


def build_jd_normalize_prompt(job: ParsedDocument) -> str:
    """Optional prompt to normalize a JD into structured requirements (JSON)."""
    return f"""Extract structured hiring requirements from this job description.

JOB DESCRIPTION:
{job.to_prompt_block()}

Return ONLY JSON:
{{
  "title": "...",
  "must_have_skills": ["..."],
  "nice_to_have_skills": ["..."],
  "min_years_experience": <number or null>,
  "responsibilities": ["..."],
  "keywords": ["..."]
}}
"""
