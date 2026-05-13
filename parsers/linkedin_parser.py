# parsers/linkedin_parser.py
#
# LinkedIn Profile Ingestion — Three approaches supported:
#
# APPROACH 1: RapidAPI LinkedIn Scraper (chosen for URL input)
#   Uses RapidAPI's "LinkedIn Profile Data" endpoint.
#   HR pastes a LinkedIn URL → API returns structured JSON.
#   Cost: Free tier gives 100 requests/month on RapidAPI.
#   Key: RAPIDAPI_KEY in .env
#   Endpoint: linkedin-api8.p.rapidapi.com
#
# APPROACH 2: LinkedIn JSON Export (chosen for file upload)
#   Candidate exports their own profile from LinkedIn Settings.
#   Settings → Data Privacy → Get a copy of your data → select Profile.
#   HR uploads the exported JSON file.
#   Zero cost. Zero ToS risk. 100% accurate data.
#
# APPROACH 3: Text Paste (fallback)
#   HR copies text from LinkedIn page, pastes into UI.
#   LLM understands LinkedIn text format naturally.
#   Zero scraping. Zero ToS risk. Works when API fails.
#
# REJECTED: Playwright/Selenium browser automation
#   LinkedIn actively blocks scrapers. Against LinkedIn ToS.
#   Fails unpredictably during demos. Not reliable enough.

import os
import re
import json
import requests
from dotenv import load_dotenv
from core.extract_structure import extract_structured_resume, ResumeResult

load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

# ── Security: sanitise input before LLM call ─────────────────────────────────
def sanitise_text(text: str) -> str:
    patterns = [
        r"ignore (previous|all|above) instructions?",
        r"you are now", r"new instructions",
        r"system prompt", r"disregard .*instructions",
        r"act as", r"forget .*told",
    ]
    for p in patterns:
        text = re.sub(p, "[REMOVED]", text, flags=re.IGNORECASE)
    return text

# ── Approach 1: RapidAPI scraper ──────────────────────────────────────────────
def fetch_via_rapidapi(linkedin_url: str) -> tuple[bool, dict, str]:
    """
    Fetches LinkedIn profile data via RapidAPI.
    Returns (success, data_dict, error_message)

    RapidAPI endpoint: linkedin-api8.p.rapidapi.com
    Free tier: 100 requests/month
    Add RAPIDAPI_KEY to your .env file.
    """
    if not RAPIDAPI_KEY:
        return False, {}, "RAPIDAPI_KEY not set in .env"

    try:
        # extract username from URL
        # handles: linkedin.com/in/rahulsharma99
        username = linkedin_url.rstrip("/").split("/in/")[-1].split("/")[0]

        response = requests.get(
            "https://linkedin-api8.p.rapidapi.com/",
            headers={
                "x-rapidapi-key"  : RAPIDAPI_KEY,
                "x-rapidapi-host" : "linkedin-api8.p.rapidapi.com"
            },
            params={"username": username},
            timeout=15
        )

        if response.status_code != 200:
            return False, {}, f"RapidAPI error {response.status_code}: {response.text[:200]}"

        data = response.json()
        return True, data, ""

    except requests.Timeout:
        return False, {}, "RapidAPI request timed out (15s)"
    except Exception as e:
        return False, {}, f"RapidAPI request failed: {str(e)}"

def map_rapidapi_to_profile(data: dict) -> dict:
    """
    Maps RapidAPI LinkedIn response to our CandidateProfile schema.
    RapidAPI returns nested objects — we flatten to our standard schema.
    """
    # extract experiences
    experiences = []
    for exp in data.get("experience", []):
        # calculate duration months from date range
        duration = None
        start = exp.get("start", {})
        end   = exp.get("end", {})
        if start and end:
            start_months = start.get("year", 0) * 12 + start.get("month", 0)
            end_months   = end.get("year", 0)   * 12 + end.get("month", 0)
            duration = max(0, end_months - start_months)
        elif start:
            # still ongoing — calculate to now
            from datetime import datetime
            now_months = datetime.now().year * 12 + datetime.now().month
            start_months = start.get("year", 0) * 12 + start.get("month", 1)
            duration = max(0, now_months - start_months)

        experiences.append({
            "role"          : exp.get("title", ""),
            "company"       : exp.get("company", exp.get("companyName", "")),
            "duration_months": duration,
            "skills_used"   : []  # RapidAPI doesn't return per-role skills
        })

    # extract education
    education = []
    for edu in data.get("education", []):
        education.append({
            "degree"   : edu.get("degree", edu.get("fieldOfStudy", "")),
            "institute": edu.get("school", edu.get("schoolName", "")),
            "cgpa"     : None,
            "year"     : edu.get("end", {}).get("year") if edu.get("end") else None
        })

    # extract skills
    skills = []
    for skill in data.get("skills", []):
        if isinstance(skill, dict):
            skills.append(skill.get("name", ""))
        elif isinstance(skill, str):
            skills.append(skill)
    skills = list(set(filter(None, skills)))

    # certifications
    certs = [c.get("name", "") for c in data.get("certifications", [])]

    # total experience
    total_months = sum(e["duration_months"] or 0 for e in experiences)
    total_years  = round(total_months / 12, 1) if total_months else None

    return {
        "name"                  : data.get("fullName", data.get("firstName", "") + " " + data.get("lastName", "")),
        "email"                 : data.get("email"),
        "phone"                 : None,
        "linkedin"              : linkedin_url,
        "github"                : data.get("github"),
        "skills"                : skills,
        "experience"            : experiences,
        "education"             : education,
        "projects"              : [],  # RapidAPI rarely returns projects
        "certifications"        : certs,
        "total_experience_years": total_years,
        "source"                : "linkedin_rapidapi"
    }

# ── Approach 2: LinkedIn JSON export ─────────────────────────────────────────
def parse_linkedin_json_export(json_path: str) -> tuple[bool, dict, str]:
    """
    Parses LinkedIn's official data export JSON.
    Candidate goes to: LinkedIn Settings → Data Privacy
    → Get a copy of your data → Profile → Request archive.
    The exported zip contains Profile.json.

    Returns (success, profile_dict, error_message)
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # LinkedIn export can be a list or dict depending on version
        if isinstance(data, list):
            data = data[0] if data else {}

        # extract positions
        experiences = []
        for pos in data.get("positions", data.get("Position", [])):
            experiences.append({
                "role"           : pos.get("title", pos.get("Title", "")),
                "company"        : pos.get("companyName", pos.get("Company Name", "")),
                "duration_months": None,
                "skills_used"    : []
            })

        # extract education
        education = []
        for edu in data.get("education", data.get("Education", [])):
            education.append({
                "degree"   : edu.get("degreeName", edu.get("Degree Name", "")),
                "institute": edu.get("schoolName", edu.get("School Name", "")),
                "cgpa"     : None,
                "year"     : None
            })

        # extract skills
        skills_raw = data.get("skills", data.get("Skills", []))
        skills = []
        for s in skills_raw:
            if isinstance(s, dict):
                skills.append(s.get("name", s.get("Name", "")))
            elif isinstance(s, str):
                skills.append(s)

        profile = {
            "name"                  : data.get("firstName", "") + " " + data.get("lastName", ""),
            "email"                 : data.get("emailAddress"),
            "phone"                 : None,
            "linkedin"              : None,
            "github"                : None,
            "skills"                : list(set(filter(None, skills))),
            "experience"            : experiences,
            "education"             : education,
            "projects"              : [],
            "certifications"        : [],
            "total_experience_years": None,
            "source"                : "linkedin_json_export"
        }

        return True, profile, ""

    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON file: {e}"
    except Exception as e:
        return False, {}, f"Failed to parse LinkedIn export: {e}"

# ── Approach 3: Text paste → LLM extraction ──────────────────────────────────
def parse_linkedin_text_paste(
        raw_text: str,
        linkedin_url: str = ""
) -> ResumeResult:
    """
    Fallback: HR pastes text copied from LinkedIn page.
    Uses same LLM extraction as resume pipeline.
    """
    if len(raw_text.strip()) < 200:
        return ResumeResult(
            filename=linkedin_url or "linkedin_paste",
            status="failed",
            error_type="validation_error",
            error_detail="Pasted text too short — paste the complete profile page"
        )

    clean_text = sanitise_text(raw_text)
    result = extract_structured_resume(
        cleaned_text=clean_text,
        filename=linkedin_url or "linkedin_paste"
    )
    if result.status == "passed" and result.resume:
        result.resume.linkedin = linkedin_url
    return result

# ── Main entry point — called by input_router ─────────────────────────────────
def parse_linkedin_profile(
        method: str,           # "rapidapi" | "json_export" | "text_paste"
        linkedin_url: str = "",
        json_path: str    = "",
        raw_text: str     = ""
) -> ResumeResult:
    """
    Unified LinkedIn parser — routes to correct approach.
    Always returns ResumeResult — same type as resume pipeline.
    Scorer receives identical CandidateProfile regardless of source.

    Args:
        method      : which approach to use
        linkedin_url: URL for rapidapi or reference
        json_path   : file path for json_export
        raw_text    : pasted text for text_paste
    """
    filename = linkedin_url or json_path or "linkedin_profile"

    # ── RapidAPI ──────────────────────────────────────────────────────────────
    if method == "rapidapi":
        success, data, error = fetch_via_rapidapi(linkedin_url)

        if not success:
            print(f"  RapidAPI failed: {error}. Falling back to text paste if available.")
            if raw_text.strip():
                print("  Falling back to text paste...")
                return parse_linkedin_text_paste(raw_text, linkedin_url)
            return ResumeResult(
                filename=filename,
                status="failed",
                error_type="api_error",
                error_detail=error
            )

        profile = map_rapidapi_to_profile(data)

        # wrap in ResumeResult manually — no LLM needed, already structured
        from core.extract_structure import Resume
        try:
            from pydantic import ValidationError
            resume_obj = Resume(**{k: v for k, v in profile.items() if k != "source"})
            result = ResumeResult(filename=filename, status="passed", resume=resume_obj)
            return result
        except Exception as e:
            return ResumeResult(
                filename=filename,
                status="failed",
                error_type="validation_error",
                error_detail=str(e)
            )

    # ── JSON export ───────────────────────────────────────────────────────────
    elif method == "json_export":
        success, profile, error = parse_linkedin_json_export(json_path)

        if not success:
            return ResumeResult(
                filename=filename,
                status="failed",
                error_type="parse_error",
                error_detail=error
            )

        from core.extract_structure import Resume
        try:
            resume_obj = Resume(**{k: v for k, v in profile.items() if k != "source"})
            return ResumeResult(filename=filename, status="passed", resume=resume_obj)
        except Exception as e:
            return ResumeResult(
                filename=filename,
                status="failed",
                error_type="validation_error",
                error_detail=str(e)
            )

    # ── Text paste ────────────────────────────────────────────────────────────
    elif method == "text_paste":
        return parse_linkedin_text_paste(raw_text, linkedin_url)

    else:
        return ResumeResult(
            filename=filename,
            status="failed",
            error_type="routing_error",
            error_detail=f"Unknown LinkedIn method: {method}"
        )