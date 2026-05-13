# core/extract_structure.py

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, ValidationError
from typing import Optional
import os
import json

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Pydantic models — define exact schema ─────────────────────────────────────

class Education(BaseModel):
    degree: str
    institute: str
    cgpa: Optional[float] = None
    year: Optional[int] = None

class Experience(BaseModel):
    role: str
    company: str
    duration_months: Optional[int] = None
    skills_used: list[str] = []

class Project(BaseModel):
    name: str
    description: Optional[str] = None
    tech_stack: list[str] = []

class Resume(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    education: list[Education] = []
    experience: list[Experience] = []
    skills: list[str] = []
    total_experience_years: Optional[float] = None
    projects: list[Project] = []
    certifications: list[str] = []

    def to_dict(self) -> dict:
        return self.model_dump()

class ResumeResult(BaseModel):

    filename: str
    status: str                          # "passed" or "failed"
    resume: Optional[Resume] = None      # present only if status == "passed"
    error_type: Optional[str] = None     # "llm_error" | "json_error" | "validation_error"
    error_detail: Optional[str] = None
    raw_llm_output: Optional[str] = None

    def to_dict(self) -> dict:
        """
        Returns the resume profile dict.
        Called by resume_parser.py to pass profile to filter and scorer.
        Returns empty dict if extraction failed.
        """
        if self.resume:
            return self.resume.to_dict()
        return {}

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert resume parser.

Extract information from the resume text and return ONLY a valid JSON object.
No explanation. No markdown. No backticks. Just raw JSON.

Follow this exact structure:
{
  "name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "linkedin": "string or null",
  "github": "string or null",
  "education": [
    {
      "degree": "string",
      "institute": "string",
      "cgpa": number or null,
      "year": number or null
    }
  ],
  "experience": [
    {
      "role": "string",
      "company": "string",
      "duration_months": number or null,
      "skills_used": ["string"]
    }
  ],
  "skills": ["string"],
  "total_experience_years": number or null,
  "projects": [
    {
      "name": "string",
      "description": "string or null",
      "tech_stack": ["string"]
    }
  ],
  "certifications": ["string"]
}

RULES:
- Return ONLY the JSON. Absolutely nothing else.
- Use null for any missing string or number fields.
- Use [] for any missing list fields.
- For duration_months: convert ranges like Jan 2023 to Jun 2023 = 6.
- For total_experience_years: sum all durations, convert to years.
- For cgpa: keep as-is. Do not convert between scales.
- Deduplicate skills. Use full names: JS = JavaScript, PY = Python.
- Extract ALL education, experience, and project entries."""

# ── Main extraction function ──────────────────────────────────────────────────
def extract_structured_resume(cleaned_text: str, filename: str) -> ResumeResult:
    """
    Takes cleaned resume text.
    Returns ResumeResult with status passed or failed.

    Three failure modes caught separately:
        llm_error        — API call failed
        json_error       — LLM returned invalid JSON
        validation_error — JSON doesn't match Resume schema
    """

    # ── Stage 1: LLM call ────────────────────────────────────────────────────
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract information from this resume:\n\n{cleaned_text}"}
            ]
        )
        raw_text = response.choices[0].message.content.strip()

    except Exception as e:
        return ResumeResult(
            filename=filename,
            status="failed",
            error_type="llm_error",
            error_detail=str(e)
        )

    # ── Stage 2: Parse JSON ──────────────────────────────────────────────────
    try:
        # defensive clean — strip markdown fences if model adds them
        clean = (
            raw_text
            .strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        data = json.loads(clean)

    except json.JSONDecodeError as e:
        return ResumeResult(
            filename=filename,
            status="failed",
            error_type="json_error",
            error_detail=str(e),
            raw_llm_output=raw_text
        )

    # ── Stage 3: Validate with Pydantic ─────────────────────────────────────
    try:
        resume = Resume(**data)
        return ResumeResult(
            filename=filename,
            status="passed",
            resume=resume
        )

    except ValidationError as e:
        return ResumeResult(
            filename=filename,
            status="failed",
            error_type="validation_error",
            error_detail=str(e),
            raw_llm_output=raw_text
        )


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = """
    Rahul Sharma
    rahul.sharma99@gmail.com | +91-9876543210
    github.com/rahulsharma99

    EDUCATION
    IIT Roorkee — B.Tech Computer Science 2020-2024 CGPA 8.6

    EXPERIENCE
    Software Engineering Intern — Google, Hyderabad
    May 2023 – July 2023
    Built log aggregation pipeline using Pub/Sub and BigQuery

    SKILLS
    Python, FastAPI, Docker, AWS, PostgreSQL, Redis

    PROJECTS
    CodeCollab — Real-time collaborative code editor
    React, Node.js, Socket.IO, Docker
    """

    result = extract_structured_resume(sample, "test_resume.pdf")

    print(f"Status : {result.status}")
    if result.status == "passed":
        print(f"Name   : {result.resume.name}")
        print(f"Skills : {result.resume.skills}")
        print(f"Exp    : {result.resume.total_experience_years} years")
        print("\nFull profile:")
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Error  : {result.error_type}")
        print(f"Detail : {result.error_detail}")