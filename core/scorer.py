# core/scorer.py

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, ValidationError
from typing import Literal
import os
import json

#Load environment
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

#Pydantic models

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

    weighted_total: float = 0.0

    recommendation: Literal[
        "strong_hire",
        "hire",
        "maybe",
        "no_hire"
    ]

    summary: str

    def to_dict(self) -> dict:
        return self.model_dump()


# Scoring Prompt

SYSTEM_PROMPT = """
You are a strict, unbiased HR evaluator with 10 years of 
experience screening candidates across top tech companies.

Your evaluations are known for being honest, calibrated, and fair.
You do not inflate scores. You do not assume skills not explicitly mentioned.
You score only what is written — nothing more, nothing less.

SCORING DIMENSIONS AND WEIGHTS:
1. skills_match       (30%)
2. experience_relevance (25%)
3. education_certs    (15%)
4. project_portfolio  (20%)
5. communication_quality (10%)

SCORE SCALE:
0-2   : Poor
3-4   : Weak
5-6   : Average
7-8   : Strong
9-10  : Excellent

CRITICAL RULES:
- Missing most required skills → skills_match < 5
- Zero relevant experience → experience_relevance < 4
- Do NOT inflate scores.
- recommendation must be exactly:
  strong_hire | hire | maybe | no_hire

Return ONLY valid JSON.

JSON structure:
{
  "candidate_name": "string",
  "skills_match": {
    "score": 0.0,
    "justification": "string"
  },
  "experience_relevance": {
    "score": 0.0,
    "justification": "string"
  },
  "education_certs": {
    "score": 0.0,
    "justification": "string"
  },
  "project_portfolio": {
    "score": 0.0,
    "justification": "string"
  },
  "communication_quality": {
    "score": 0.0,
    "justification": "string"
  },
  "recommendation": "strong_hire | hire | maybe | no_hire",
  "summary": "string"
}
"""

# ── Weights ───────────────────────────────────────────────────

WEIGHTS = {
    "skills_match": 0.30,
    "experience_relevance": 0.25,
    "education_certs": 0.15,
    "project_portfolio": 0.20,
    "communication_quality": 0.10,
}

#Weighted Score Calculation

def calculate_weighted_total(score: CandidateScore) -> float:

    return round(
        score.skills_match.score * WEIGHTS["skills_match"] +
        score.experience_relevance.score * WEIGHTS["experience_relevance"] +
        score.education_certs.score * WEIGHTS["education_certs"] +
        score.project_portfolio.score * WEIGHTS["project_portfolio"] +
        score.communication_quality.score * WEIGHTS["communication_quality"],
        2
    )

#Score One Candidate

def score_candidate(
        jd_requirements: dict,
        candidate_profile: dict
) -> CandidateScore | None:

    candidate_name = candidate_profile.get("name", "Unknown")


    scoring_profile = {
        "name": candidate_name,
        "skills": candidate_profile.get("skills", []),
        "total_experience_years":
            candidate_profile.get("total_experience_years"),

        "experience":
            candidate_profile.get("experience", []),

        "education":
            candidate_profile.get("education", []),

        "projects":
            candidate_profile.get("projects", []),

        "certifications":
            candidate_profile.get("certifications", []),
    }

    user_message = f"""
Score this candidate strictly against the job requirements.

JOB REQUIREMENTS:
{json.dumps(jd_requirements, indent=2)}

CANDIDATE PROFILE:
{json.dumps(scoring_profile, indent=2)}

Be strict. Score only what is explicitly present.
"""


    try:

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        raw_text = response.choices[0].message.content.strip()

    except Exception as e:

        print(f"LLM call failed for {candidate_name} — {e}")
        return None

    #Parse JSON
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

        print(f"JSON parse failed for {candidate_name} — {e}")
        print(f"Raw output: {raw_text[:200]}")
        return None

    #Validate
    try:

        score = CandidateScore(**data)

        # never trust LLM arithmetic
        score.weighted_total = calculate_weighted_total(score)

        return score

    except ValidationError as e:

        print(f"Validation failed for {candidate_name} — {e}")
        return None


# Batch Scoring

def score_all_candidates(
        passed_resumes: list,
        jd_requirements: dict
) -> tuple[list[CandidateScore], list[dict]]:

    scored = []
    errored = []

    print(f"\nScoring {len(passed_resumes)} candidate(s)...\n")

    for i, profile in enumerate(passed_resumes, 1):

        name = profile.get("name", f"Candidate {i}")

        print(f"[{i}/{len(passed_resumes)}] Scoring {name}...")

        score = score_candidate(
            jd_requirements=jd_requirements,
            candidate_profile=profile
        )

        if score:

            scored.append(score)

            print(f"Weighted Total: {score.weighted_total}/10")
            print(f"Recommendation: {score.recommendation.upper()}")
            print()

        else:

            errored.append({
                "name": name,
                "reason": "scoring failed"
            })

    return scored, errored


# Save Scores

def save_scores(
        scored: list[CandidateScore],
        output_path: str = "../output/scores.json"
):

    from pathlib import Path

    Path(output_path).parent.mkdir(exist_ok=True)

    data = [s.to_dict() for s in scored]

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Scores saved → {output_path}")