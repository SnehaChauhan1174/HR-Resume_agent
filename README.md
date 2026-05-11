**## Setup Instructions
```bash
git clone https://github.com/YOUR_USERNAME/hr-resume-shortlisting-agent
cd hr-resume-shortlisting-agent
pip install -r requirements.txt

# Create .env file and add:
# GROQ_API_KEY=your-key-here

python jd_parser.py
```

## Technical Stack & Decision Log

### LLM: Llama 3.3 70B (via Groq API)
- Provider: Groq
- Model: llama-3.3-70b-versatile
- Why chosen: Groq provides free API access with no billing setup 
  required. Llama 3.3 70B is an open-source model with strong 
  instruction-following capability — returns clean structured JSON 
  consistently. Groq's inference engine is significantly faster than 
  hosted alternatives (OpenAI, Anthropic) due to custom LPU hardware, 
  making it ideal for batch resume processing where speed matters.
- Alternatives considered: Gemini 2.0 Flash (comparable, Google billing 
  setup needed), Claude Sonnet 4 (stronger reasoning but paid), GPT-4o 
  (paid, higher cost per token), Mistral Large (weaker on structured 
  output consistency).

### Agent Architecture: Sequential Python Pipeline
- Pattern: Parse JD → Parse Resume → Score → Rank → Report
- Why no framework: Workflow is deterministic and sequential. No dynamic 
  tool selection or multi-agent coordination needed. Direct API calls are 
  more transparent, auditable, and easier to document for security review.
- LangGraph considered: Would be appropriate if agent needed conditional 
  branching (e.g. LinkedIn vs PDF input decision) or score-based routing. 
  Planned for production version.

### JD Parsing: Pure LLM Extraction
Four approaches evaluated:
1. Pure LLM (chosen) — handles any format, phrasing, synonyms
2. Regex + spaCy (rejected) — brittle, breaks on phrasing variation
3. Hybrid section-split + LLM (future) — better token cost at scale
4. Embeddings (rejected) — returns single float, incompatible with rubric

### PDF Parsing: pdfplumber
- Chosen over PyMuPDF — better multi-column layout handling
- Chosen over pdfminer — simpler API, less boilerplate
- PyPDF2 deprecated, ruled out

### Output Validation: Pydantic v2
- Enforces schema on every LLM response before downstream use
- Weighted total recalculated in Python — LLM math not trusted
- Invalid responses raise clear errors, never silently corrupt data

## Security Mitigations

| Risk | Mitigation |
|------|-----------|
| Prompt Injection | sanitise_input() strips injection patterns before LLM call |
| API Key Exposure | python-dotenv + .env + .gitignore — key never hardcoded |
| PII in Logs | mask_pii_for_logging() masks email/phone before any log write |
| Hallucination | Pydantic schema validation + Python recalculates weighted total |
| Unauthorised Access | Planned: OAuth on Streamlit endpoint in production |

## Sample Output

role: AI Enablement Intern

Experience : 0+ years
 Education : Currently pursuing a degree in Computer Science or related field

 Required skills (3)
    • Python
    • APIs
    • written and verbal communication skills

  Preferred Skills (7):
    • LLMs
    • ChatGPT
    • Claude
    • LangChain
    • CrewAI
    • Git
    • GitHub

  Certifications:
    • cloud certification
    • AI course on Coursera or DeepLearning.AI

  Key Responsibilities:
    • Build and prototype AI agent solutions
    • Document technical decisions and architecture clearly
    • Test agents against real data and iterate on results
    • Present demos to the team weekly

  Nice to Have:
    • Experience with Streamlit or Gradio
    • Interest in responsible AI and bias mitigation

## Resume parser.py
- implemented extract function using pdfplumbe
- implemented 3 layers for cleaning the text
    - special characters replaced
    - formatting errors
    - section merged with content
- batch loading of functions
- PII masking for logs

### Input Validation: validator.py

A pre-flight validation step was added between resume parsing and LLM 
scoring. Resumes that fail validation are rejected with a specific reason 
before any LLM call is made.

Checks performed:
- Minimum text length (200 chars)
- Presence of at least one core section (experience/education/skills)
- Word count threshold (150 words minimum)
- Noise rate check (garbled character ratio)

Reasoning: LLMs hallucinate structure from noisy input — a corrupt resume 
can produce plausible-looking but fabricated scores. Early rejection with 
a clear reason is more useful than a downstream hallucination. It also 
saves API tokens and latency.

## What I Would Add With More Time
- Hybrid section-splitting for lower token cost at scale
- LangGraph for conditional branching on input type
- LinkedIn JSON profile ingestion
- OAuth authentication on Streamlit endpoint
- LangSmith tracing for observability**


