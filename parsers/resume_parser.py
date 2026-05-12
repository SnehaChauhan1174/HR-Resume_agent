from core.extractor import extract_resume_text
from core.cleaner import fix_layer1, fix_layer2, fix_sections
from core.extract_structure import extract_structured_resume
from core.filter import run_filters
from parsers.jd_parser import parse_jd

import os
import json
from pathlib import Path
from datetime import datetime

# so that it don't take paths relative to current directory
BASE_DIR = Path(__file__).resolve().parent

RESUME_FOLDER = BASE_DIR.parent / "resumes"
OUTPUT_FOLDER = BASE_DIR / "output"
LOG_FILE      = BASE_DIR.parent / "output" / "pipeline_log.json"
JD_FILE       = BASE_DIR / "sample_jd.txt"

# ── Step printer
def step(number: int, title: str):

    print(f"  STEP {number} — {title}")


# ── Main pipeline
def run_pipeline():

    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

    # ── STEP 1: Parse JD
    step(1, "Parsing Job Description")

    try:
        with open(JD_FILE, "r") as f:
            jd_text = f.read()
        jd_requirements = parse_jd(jd_text)
        print(f"  Role   : {jd_requirements.role_title}")
        print(f"  Skills : {len(jd_requirements.required_skills)} required")

        # save jd output
        with open(f"{OUTPUT_FOLDER}jd_output.json", "w") as f:
            json.dump(jd_requirements.model_dump(), f, indent=2)
        print(f"  Saved  : {OUTPUT_FOLDER}jd_output.json")

    except FileNotFoundError:
        print(f"  ERROR: {JD_FILE} not found.")
        return [], [], []

    except ValueError as e:
        print(f"  ERROR: JD parsing failed — {e}")
        return [], [], []

    # ── STEP 2: Process Resumes ──
    step(2, "Processing Resumes")

    pdf_files = list(Path(RESUME_FOLDER).glob("*.pdf"))

    if not pdf_files:
        print(f"  ERROR: No PDFs found in {RESUME_FOLDER}")
        return [], [], []

    print(f"  Found {len(pdf_files)} resume(s)\n")

    passed   = []   # structured profile — ready for scoring
    failed   = []   # extraction failed — LLM or Pydantic error
    rejected = []   # filter rejected — missing skills, low quality

    for i, pdf_path in enumerate(pdf_files, 1):

        print(f"  [{i}/{len(pdf_files)}] {pdf_path.name}")

        # ── Stage A: Extract + Clean text ──
        try:
            raw_text = extract_resume_text(str(pdf_path))

            if not raw_text.strip():
                raise ValueError("Empty text extracted — likely image-based PDF")

            cleaned_text = fix_layer1(raw_text)
            cleaned_text = fix_layer2(cleaned_text)
            cleaned_text = fix_sections(cleaned_text)

        except Exception as e:
            print(f"    ✗ Text extraction failed — {e}")
            failed.append({
                "file": pdf_path.name,
                "stage": "extraction",
                "reason": str(e)
            })
            continue   # skip to next resume

        # ── Stage B: LLM structured extraction ───
        res = extract_structured_resume(cleaned_text, pdf_path.name)

        if res.status != "passed":
            print(f"    ✗ Structured extraction failed — "
                  f"{res.error_type}: {res.error_detail[:80]}")
            failed.append({
                "file": pdf_path.name,
                "stage": "llm_extraction",
                "reason": f"{res.error_type}: {res.error_detail}"
            })
            continue   # skip to next resume

        # ── Stage C: Filter — quality + knockout rules
        # run_filters needs: cleaned text + structured profile + jd requirements
        is_valid, reason = run_filters(
            resume_text=cleaned_text,
        )

        if not is_valid:
            print(f"Filtered out — {reason}")
            rejected.append({
                "file": pdf_path.name,
                "candidate_name": res.to_dict().get("name", "Unknown"),
                "stage": "filter",
                "reason": reason
            })
            continue   # skip to next resume


        print(f"Passed — {res.to_dict().get('name', pdf_path.stem)}")
        passed.append(res.to_dict())


    step(3, "Saving Pipeline Log")

    log = {
        "run_timestamp"  : datetime.now().isoformat(),
        "jd_role"        : jd_requirements.role_title,
        "total_found"    : len(pdf_files),
        "passed_count"   : len(passed),
        "failed_count"   : len(failed),
        "rejected_count" : len(rejected),
        "failed"         : failed,
        "rejected"       : rejected,
        # note: passed resumes not logged here — resume text is PII
        "passed_names"   : [
            r.get("name") or "Unknown"
            for r in passed

        ]
    }

    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)



    print(f"  PIPELINE SUMMARY")

    print(f"  Total found  : {len(pdf_files)}")
    print(f"  Passed       : {len(passed)}")
    print(f"  Failed       : {len(failed)}")
    print(f"  Rejected     : {len(rejected)}")
    print(f"  Log saved    : {LOG_FILE}")


    if failed:
        print("  Failed resumes:")
        for f in failed:
            print(f"    • {f['file']} → {f['reason']}")

    if rejected:
        print("\n  Rejected resumes:")
        for r in rejected:
            print(f"    • {r['file']} → {r['reason']}")

    # return passed for next step — scoring
    return passed, failed, rejected


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    passed_resumes, failed_resumes, rejected_resumes = run_pipeline()

    if passed_resumes:
        print(f"\n  {len(passed_resumes)} resume(s) ready for scoring.")

    else:
        print("\n  No resumes passed pipeline. Check resumes/ folder.\n")