# core/scorer.py

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Literal
import os
import json

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Pydantic models ───────────────────────────────────────────────────────────

class DimensionScore(BaseModel):
    score: float = Field(ge=0, le=10)
    justification: str

class CandidateScore(BaseModel):
    candidate_name: str
    skills_match: DimensionScore
    experience_relevance: DimensionScore
    education_certs: DimensionScore
    project_portfolio: DimensionScore
    communication_quality: DimensionScore
    weighted_total: float = 0.0         # calculated in Python — never trusted from LLM
    recommendation: Literal["strong_hire", "hire", "maybe", "no_hire"]
    summary: str

    def to_dict(self) -> dict:
        return self.model_dump()

# ── Scoring prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a strict, unbiased HR evaluator with 10 years of 
experience screening candidates across top tech companies.

Your evaluations are known for being honest, calibrated, and fair.
You do not inflate scores. You do not assume skills not explicitly mentioned.
You score only what is written — nothing more, nothing less.

SCORING DIMENSIONS AND WEIGHTS:
1. skills_match       (30%) — how many required skills the candidate has
2. experience_relevance (25%) — is their experience in the right domain
3. education_certs    (15%) — does education meet or exceed requirements
4. project_portfolio  (20%) — quality and relevance of projects shown
5. communication_quality (10%) — clarity, structure, impact of resume writing

SCORE SCALE — be strict:
0  - 2  : Poor. Completely irrelevant or missing entirely.
3  - 4  : Weak. Major gaps, minimal relevant content.
5  - 6  : Average. Some relevant elements but significant gaps remain.
7  - 8  : Strong. Meets most requirements with only minor gaps.
9  - 10 : Excellent. Exceeds requirements. Evidence of outstanding quality.

CRITICAL RULES:
- A candidate missing most required skills MUST score below 5 on skills_match.
- A candidate with zero relevant work experience MUST score below 4 on experience_relevance.
- Do NOT give everyone 7+. Reserve 8+ for genuinely strong candidates.
- Justification must be one specific sentence explaining exactly why that score was given.
- recommendation must be exactly one of: strong_hire, hire, maybe, no_hire
- strong_hire: weighted_total >= 8.0
- hire: weighted_total >= 6.5
- maybe: weighted_total >= 5.0
- no_hire: weighted_total < 5.0

Return ONLY valid JSON. No markdown. No explanation. No code fences.

JSON structure:
{
  "candidate_name": "string",
  "skills_match": {
    "score": 0.0,
    "justification": "one specific sentence"
  },
  "experience_relevance": {
    "score": 0.0,
    "justification": "one specific sentence"
  },
  "education_certs": {
    "score": 0.0,
    "justification": "one specific sentence"
  },
  "project_portfolio": {
    "score": 0.0,
    "justification": "one specific sentence"
  },
  "communication_quality": {
    "score": 0.0,
    "justification": "one specific sentence"
  },
  "recommendation": "strong_hire | hire | maybe | no_hire",
  "summary": "two sentence overall assessment"
}"""

# ── Weight constants ──────────────────────────────────────────────────────────
WEIGHTS = {
    "skills_match"         : 0.30,
    "experience_relevance" : 0.25,
    "education_certs"      : 0.15,
    "project_portfolio"    : 0.20,
    "communication_quality": 0.10,
}

# ── Weighted total — always calculated in Python ──────────────────────────────
def calculate_weighted_total(score: CandidateScore) -> float:
    """
    Never trust LLM arithmetic.
    Always recalculate weighted total in Python.
    """
    return round(
        score.skills_match.score          * WEIGHTS["skills_match"]          +
        score.experience_relevance.score  * WEIGHTS["experience_relevance"]  +
        score.education_certs.score       * WEIGHTS["education_certs"]       +
        score.project_portfolio.score     * WEIGHTS["project_portfolio"]     +
        score.communication_quality.score * WEIGHTS["communication_quality"],
        2
    )

# ── Main scorer function ──────────────────────────────────────────────────────
def score_candidate(
        jd_requirements: dict,
        candidate_profile: dict
) -> CandidateScore | None:
    """
    Takes JD requirements dict and candidate profile dict.
    Returns validated CandidateScore object.
    Returns None if scoring fails — caller handles gracefully.
    """

    candidate_name = candidate_profile.get("name", "Unknown")

    # ── Build user message ────────────────────────────────────────────────────
    # strip PII from profile before sending — email, phone not needed for scoring
    scoring_profile = {
        "name"                  : candidate_name,
        "skills"                : candidate_profile.get("skills", []),
        "total_experience_years": candidate_profile.get("total_experience_years"),
        "experience"            : candidate_profile.get("experience", []),
        "education"             : candidate_profile.get("education", []),
        "projects"              : candidate_profile.get("projects", []),
        "certifications"        : candidate_profile.get("certifications", []),
    }

    user_message = f"""Score this candidate strictly against the job requirements.

JOB REQUIREMENTS:
{json.dumps(jd_requirements, indent=2)}

CANDIDATE PROFILE:
{json.dumps(scoring_profile, indent=2)}

Be strict. Score only what is explicitly present in the candidate profile."""

    # ── LLM call ─────────────────────────────────────────────────────────────
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message}
            ]
        )
        raw_text = response.choices[0].message.content.strip()

    except Exception as e:
        print(f"    ✗ LLM call failed for {candidate_name} — {e}")
        return None

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
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
        print(f"    ✗ JSON parse failed for {candidate_name} — {e}")
        print(f"      Raw output: {raw_text[:200]}")
        return None

    # ── Validate with Pydantic ────────────────────────────────────────────────
    try:
        score = CandidateScore(**data)

        # CRITICAL — always recalculate, never trust LLM math
        score.weighted_total = calculate_weighted_total(score)

        return score

    except ValidationError as e:
        print(f"    ✗ Validation failed for {candidate_name} — {e}")
        return None

# ── Batch scoring ─────────────────────────────────────────────────────────────
def score_all_candidates(
        passed_resumes: list,
        jd_requirements: dict
) -> tuple[list[CandidateScore], list[dict]]:
    """
    Scores all passed resumes.

    Args:
        passed_resumes   : list of ResumeResult objects from extract_structure
        jd_requirements  : jd_requirements.model_dump() from jd_parser

    Returns:
        scored  : list of CandidateScore objects
        errored : list of dicts for resumes that failed scoring
    """
    scored  = []
    errored = []

    print(f"\n  Scoring {len(passed_resumes)} candidate(s)...\n")

    for i, res in enumerate(passed_resumes, 1):
        profile = res.to_dict()
        name    = profile.get("name", f"Candidate {i}")

        print(f"  [{i}/{len(passed_resumes)}] Scoring {name}...")

        score = score_candidate(
            jd_requirements=jd_requirements,
            candidate_profile=profile
        )

        if score:
            scored.append(score)
            print(f"    ✓ {name}")
            print(f"      Skills        : {score.skills_match.score}/10")
            print(f"      Experience    : {score.experience_relevance.score}/10")
            print(f"      Education     : {score.education_certs.score}/10")
            print(f"      Projects      : {score.project_portfolio.score}/10")
            print(f"      Communication : {score.communication_quality.score}/10")
            print(f"      ─────────────────────────────")
            print(f"      Weighted Total: {score.weighted_total}/10")
            print(f"      Recommendation: {score.recommendation.upper()}")
            print()
        else:
            errored.append({
                "file"  : res.filename,
                "name"  : name,
                "reason": "scoring failed — see logs"
            })

    return scored, errored

# ── Save scores to output ─────────────────────────────────────────────────────
def save_scores(scored: list[CandidateScore], output_path: str = "output/scores.json"):
    """
    Saves all candidate scores to output/scores.json.
    This is your sample output for the submission.
    """
    from pathlib import Path
    Path(output_path).parent.mkdir(exist_ok=True)

    data = [s.to_dict() for s in scored]
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Scores saved → {output_path}")

# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    sample_jd = {
        "role_title"          : "AI Enablement Intern",
        "required_skills"     : ["Python", "APIs", "communication"],
        "preferred_skills"    : ["LLMs", "LangChain", "Git"],
        "experience_years_min": 0,
        "education_required"  : "Computer Science degree",
        "certifications"      : [],
        "key_responsibilities": ["Build AI agents", "Document decisions"],
        "nice_to_have"        : ["Streamlit", "responsible AI"]
    }

    # Strong candidate
    strong_profile = {
        "name"                  : "Rahul Sharma",
        "skills"                : ["Python", "FastAPI", "Docker", "AWS", "LangChain", "Git"],
        "total_experience_years": 0.5,
        "experience"            : [
            {"role": "SWE Intern", "company": "Google",
             "duration_months": 3, "skills_used": ["Python", "BigQuery"]}
        ],
        "education"             : [
            {"degree": "B.Tech Computer Science",
             "institute": "IIT Roorkee", "cgpa": 8.6, "year": 2024}
        ],
        "projects"              : [
            {"name": "AI Agent", "description": "LLM-based task automation",
             "tech_stack": ["Python", "LangChain", "FastAPI"]}
        ],
        "certifications"        : ["AWS Certified Solutions Architect"]
    }

    # Weak candidate
    weak_profile = {
        "name"                  : "John Smith",
        "skills"                : ["Cooking", "Menu Planning", "Food Safety"],
        "total_experience_years": 5.0,
        "experience"            : [
            {"role": "Head Chef", "company": "Hotel Grand",
             "duration_months": 60, "skills_used": ["Cooking"]}
        ],
        "education"             : [
            {"degree": "Diploma in Culinary Arts",
             "institute": "Culinary School", "cgpa": None, "year": 2018}
        ],
        "projects"              : [],
        "certifications"        : ["Food Safety Certificate"]
    }

    print("="*55)
    print("  SCORER TEST")
    print("="*55)

    for profile in [strong_profile, weak_profile]:
        print(f"\nScoring: {profile['name']}")
        print("-"*40)
        score = score_candidate(sample_jd, profile)
        if score:
            print(f"Skills        : {score.skills_match.score}/10 — {score.skills_match.justification}")
            print(f"Experience    : {score.experience_relevance.score}/10 — {score.experience_relevance.justification}")
            print(f"Education     : {score.education_certs.score}/10 — {score.education_certs.justification}")
            print(f"Projects      : {score.project_portfolio.score}/10 — {score.project_portfolio.justification}")
            print(f"Communication : {score.communication_quality.score}/10 — {score.communication_quality.justification}")
            print(f"{'─'*40}")
            print(f"Weighted Total: {score.weighted_total}/10")
            print(f"Recommendation: {score.recommendation.upper()}")
            print(f"Summary       : {score.summary}")