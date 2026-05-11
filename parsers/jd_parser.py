from groq import Groq
import json
import re
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Pydantic schema — defines what the LLM MUST return
class JDRequirements(BaseModel):
    role_title:str
    required_skills:List[str]
    preferred_skills:List[str]
    experience_years_min:int
    education_required:str
    certifications:List[str]
    key_responsibilities:List[str]
    nice_to_have:List[str]

# ── System prompt — tells the model exactly how to behave

SYSTEM_PROMPT = """You are an expert HR analyst with 10 years of experience 
reading job descriptions across tech companies.
 
Your job is to extract structured hiring requirements from a job description.
 
Rules:
- Return ONLY valid JSON. No markdown. No explanation. No code fences.
- required_skills: only skills explicitly marked as required or must-have
- preferred_skills: skills marked as preferred, good to have, or a plus
- experience_years_min: extract the minimum number only.
  If range is 3-5 years return 3.
  If stated as half a decade return 5.
  If not mentioned return 0.
- certifications: only actual certifications like AWS Certified or PMP.
  Do not include degrees here.
- If a field has no data return an empty list [] or empty string.
 
JSON structure to return:
{
  "role_title": "string",
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1"],
  "experience_years_min": 0,
  "education_required": "string",
  "certifications": ["cert1"],
  "key_responsibilities": ["resp1", "resp2"],
  "nice_to_have": ["item1"]
}"""

def sanitise_input(text:str)->str:
    patterns=[
        r"ignore (previous|all|above) instructions?",
        r"you are now",
        r"new instructions",
        r"system prompt",
        r"disregard .*instructions",
        r"forget .*told",
        r"act as",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "[REMOVED]", text, flags=re.IGNORECASE)
    return text

# main parser function
def parse_jd(jd_text:str)->JDRequirements:
    if not jd_text.strip():
        raise ValueError("JD text is empty. Please provide a job description.")

    jd_text=sanitise_input(jd_text)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=list([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract requirements from this job description:\n\n{jd_text}"}
        ])
    )
    raw_text = response.choices[0].message.content.strip()

    # Clean up in case model adds markdown fences despite instructions
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
    # Parse JSON and validate through Pydantic
    try:
        data = json.loads(raw_text)
        requirements = JDRequirements(**data)
        return requirements

    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON.\nError: {e}\nRaw response: {raw_text}")

    except Exception as e:
        raise ValueError(f"Schema validation failed.\nError: {e}")


def print_requirements(req: JDRequirements):
    print("\n"+"="*55)
    print(f"role: {req.role_title}")
    print("="*55)
    print(f"Experience : {req.experience_years_min}+ years")
    print(f" Education : {req.education_required}")
    print(f"\n Required skills ({len(req.required_skills)}")
    for s in req.required_skills:
        print(f"    • {s}")
    print(f"\n  Preferred Skills ({len(req.preferred_skills)}):")
    for s in req.preferred_skills:
        print(f"    • {s}")

    if req.certifications:
        print(f"\n  Certifications:")
        for c in req.certifications:
            print(f"    • {c}")

    print(f"\n  Key Responsibilities:")
    for r in req.key_responsibilities:
        print(f"    • {r}")

    if req.nice_to_have:
        print(f"\n  Nice to Have:")
        for n in req.nice_to_have:
            print(f"    • {n}")

    print()


# ── Entry point
if __name__ == "__main__":

    # Read from file if it exists, otherwise use inline sample
    jd_file = "sample_jd.txt"

    if os.path.exists(jd_file):
        print(f"Reading JD from {jd_file}...")
        with open(jd_file, "r") as f:
            jd_text = f.read()
    else:
        print("sample_jd.txt not found. Using inline sample JD...")
        jd_text = """
        Job Title: AI Enablement Intern
 
        We are looking for a motivated AI Enablement Intern to help us build
        AI-powered tools. You will prototype, test, and document AI solutions.
 
        Requirements (Must Have):
        - Basic programming experience in Python
        - Understanding of APIs and how to make API calls
        - Strong written and verbal communication skills
        - Currently pursuing a degree in Computer Science or related field
 
        Preferred Skills:
        - Exposure to LLMs or AI tools like ChatGPT or Claude
        - Familiarity with LangChain or CrewAI
        - Experience with Git and GitHub
 
        Certifications (Plus):
        - Any cloud certification is a bonus
        - Completion of any AI course on Coursera or DeepLearning.AI
 
        Responsibilities:
        - Build and prototype AI agent solutions
        - Document technical decisions and architecture clearly
        - Test agents against real data and iterate on results
        - Present demos to the team weekly
 
        Nice to Have:
        - Experience with Streamlit or Gradio
        - Interest in responsible AI and bias mitigation
        """

    print("Parsing JD with Gemini...")

    try:
        requirements = parse_jd(jd_text)

        # Print to terminal
        print_requirements(requirements)

        # Save raw JSON output for inspection and DEVLOG
        output = requirements.model_dump()
        with open("../output/jd_output.json", "w") as f:
            json.dump(output, f, indent=2)

        print("Raw JSON saved to jd_output.json")


    except ValueError as e:
        print(f"\nError: {e}")

