# pipeline entry point
# connects every module in order:
# parse jd -> parse resume -> validate -> score -> rank ->repot

import json
from parsers.jd_parser import parse_jd
from parsers.resume_parser import parse_all_resumes

# from core.validator import validate_resume
# from core.scorer import score_candidate
# from core.ranker import rank_candidates
# from core.report import generate_report

# config
JD_FILE = "sample_jd.txt"
RESUMES_FOLDER = "resumes/"
OUTPUT_FOLDER = "output/"

# def step(number:int, title:str):
#     print(f"\n{'='+50}")
#     print(f" STEP {number} - {title}")
#     print(f"{'='*50}")

# main pipeline

def run_pipeline():
    print("   HR RESUME SHORTLISTING AGENT")
    print("   Powered by Llama 3.3 70B via Groq")

    # step 1: parse jd
    print(f"1,parsing job description")
    try:
        with open(JD_FILE,"r") as f:
            jd_text = f.read()
        jd_requirements = parse_jd(jd_text)
        print(f"  Role    : {jd_requirements.role_title}")
        print(f"  Exp Min : {jd_requirements.experience_years_min}+ years")
        print(f"  Skills  : {len(jd_requirements.required_skills)} required, "
              f"{len(jd_requirements.preferred_skills)} preferred")

        import os
        os.makedirs(OUTPUT_FOLDER,exist_ok=True)
        with open(f"{OUTPUT_FOLDER}jd_output.json","w") as f:
            json.dump(jd_requirements.model_dump(),f,indent=2)
        print(f"  Saved   : {OUTPUT_FOLDER}jd_output.json")

    except FileNotFoundError:
        print(f"  ERROR: {JD_FILE} not found.")
        print("  Create a sample_jd.txt file in the project root.")
        return
    except ValueError as e:
        print(f"  ERROR: JD parsing failed — {e}")
        return






