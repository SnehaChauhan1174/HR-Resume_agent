# core/override_logger.py
#
# Human-in-the-Loop override system.
# Brief requirement: "HR can adjust scores; agent logs the change and reason"
#
# STORAGE APPROACH: JSONL file (append-only)
# One JSON object per line. Human readable. No database needed.
# SQLite would be the production upgrade — documented in README.

import json
from datetime import datetime
from pathlib import Path

OVERRIDE_LOG_FILE = "output/override_log.jsonl"

WEIGHTS = {
    "skills_match"         : 0.30,
    "experience_relevance" : 0.25,
    "education_certs"      : 0.15,
    "project_portfolio"    : 0.20,
    "communication_quality": 0.10,
}

def recalculate_weighted_total(scores: dict) -> float:
    return round(
        sum(scores.get(dim, 0) * w for dim, w in WEIGHTS.items()), 2
    )

def get_recommendation(weighted_total: float) -> str:
    if weighted_total >= 8.0: return "strong_hire"
    if weighted_total >= 6.5: return "hire"
    if weighted_total >= 5.0: return "maybe"
    return "no_hire"

def log_override(
        candidate_name: str,
        dimension: str,
        original_score: float,
        new_score: float,
        reason: str,
        all_current_scores: dict,
        logged_by: str = "HR"
) -> dict:
    """
    Logs override and returns updated weighted total + recommendation.
    Called by Streamlit UI when HR submits an override.
    """
    Path("output").mkdir(exist_ok=True)

    new_weighted_total = recalculate_weighted_total(all_current_scores)
    new_recommendation = get_recommendation(new_weighted_total)

    entry = {
        "timestamp"         : datetime.now().isoformat(),
        "candidate_name"    : candidate_name,
        "dimension"         : dimension,
        "original_score"    : original_score,
        "new_score"         : new_score,
        "score_delta"       : round(new_score - original_score, 2),
        "reason"            : reason,
        "logged_by"         : logged_by,
        "new_weighted_total": new_weighted_total,
        "new_recommendation": new_recommendation,
        "all_scores_after"  : all_current_scores,
    }

    with open(OVERRIDE_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return {
        "weighted_total" : new_weighted_total,
        "recommendation" : new_recommendation,
    }

def get_all_overrides() -> list[dict]:
    if not Path(OVERRIDE_LOG_FILE).exists():
        return []
    overrides = []
    with open(OVERRIDE_LOG_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                overrides.append(json.loads(line))
    return overrides

def get_overrides_for_candidate(candidate_name: str) -> list[dict]:
    return [o for o in get_all_overrides() if o["candidate_name"] == candidate_name]