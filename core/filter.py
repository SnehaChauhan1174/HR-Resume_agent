
# core/filter.py
# Quality gate — catches corrupt/garbage input before wasting an LLM call.
# Business logic (skill match, experience threshold) is intentionally
# NOT here — the scorer's rubric handles that through dimension scores.

import re

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_CHAR_COUNT  = 200    # below this — likely image-based or empty PDF
MIN_WORD_COUNT  = 150    # below this — resume is too short to be real
MAX_NOISE_RATIO = 0.05   # above this — too many garbage characters
MAX_CID_COUNT   = 10     # above this — font corruption too severe
MIN_REAL_RATIO  = 0.50   # below this — less than 50% recognisable words

# ── Core sections — at least one must exist ───────────────────────────────────
REQUIRED_SECTIONS = [
    "experience", "education", "skills",
    "work", "employment", "qualification"
]

# ── Individual checks — each returns (passed: bool, reason: str) ──────────────

def check_minimum_length(text: str) -> tuple[bool, str]:
    """Catches image-based or completely empty PDFs."""
    if len(text.strip()) < MIN_CHAR_COUNT:
        return False, (
            f"Text too short ({len(text.strip())} chars) — "
            f"PDF may be image-based or empty"
        )
    return True, ""


def check_word_count(text: str) -> tuple[bool, str]:
    """Catches PDFs with almost no readable content."""
    word_count = len(text.split())
    if word_count < MIN_WORD_COUNT:
        return False, (
            f"Too few words ({word_count}) — "
            f"resume appears incomplete"
        )
    return True, ""


def check_section_presence(text: str) -> tuple[bool, str]:
    """
    At least one core resume section must exist.
    If none found — this is not a resume at all.
    """
    text_lower = text.lower()
    found = [s for s in REQUIRED_SECTIONS if s in text_lower]
    if not found:
        return False, (
            "No recognisable resume sections found "
            "(experience / education / skills) — "
            "file may not be a resume"
        )
    return True, ""


def check_noise_ratio(text: str) -> tuple[bool, str]:
    """
    Measures ratio of garbage characters to total characters.
    Catches corrupt PDF extraction where encoding failed.
    Allowed chars: letters, digits, whitespace, common punctuation.
    """
    if not text:
        return False, "Empty text"

    allowed = re.compile(r'[a-zA-Z0-9\s\.\,\-\+\@\/\|\(\)\[\]\:\#\%\&\*\!\?\'\"\\]')
    garbage = [ch for ch in text if not allowed.match(ch)]
    ratio = len(garbage) / len(text)

    if ratio > MAX_NOISE_RATIO:
        return False, (
            f"High noise ratio ({ratio:.1%}) — "
            f"possible corrupt PDF extraction"
        )
    return True, ""


def check_real_word_ratio(text: str) -> tuple[bool, str]:
    """
    Checks what fraction of tokens look like real words.
    If less than 50% are alphabetic strings — text is mostly garbage.
    """
    words = text.split()
    if not words:
        return False, "No words found"

    real = [w for w in words if re.match(r'^[a-zA-Z]{2,}$', w)]
    ratio = len(real) / len(words)

    if ratio < MIN_REAL_RATIO:
        return False, (
            f"Low real-word ratio ({ratio:.1%}) — "
            f"resume text appears garbled or binary"
        )
    return True, ""


# ── Main filter function — runs all checks in order ───────────────────────────
def run_filters(resume_text: str) -> tuple[bool, str]:
    """
    Runs all quality checks on extracted resume text.
    Stops at first failure — no point running further checks.

    Args:
        resume_text: cleaned text from resume_parser pipeline

    Returns:
        (True, "")              — all checks passed, send to LLM
        (False, "reason here")  — failed, log reason, skip LLM call

    Design note:
        Business logic (skill match, experience threshold, keyword
        screening) is intentionally NOT here. The scorer's rubric
        handles those through dimension scores — a candidate missing
        required skills will score low on skills_match and receive
        a no_hire recommendation. Duplicating that logic here would
        create two sources of truth and make the system harder to
        maintain and explain.
    """
    checks = [
        check_minimum_length,
        check_word_count,
        check_section_presence,
        check_noise_ratio,
        check_real_word_ratio,
    ]

    for check in checks:
        passed, reason = check(resume_text)
        if not passed:
            return False, reason

    return True, ""


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Test 1 — good resume text
    good_text = """
    EDUCATION
    Indian Institute of Technology Roorkee 2020-2024
    B.Tech Computer Science CGPA 8.6

    EXPERIENCE
    Software Engineering Intern Google Hyderabad May 2023 July 2023
    Built real-time log aggregation pipeline using PubSub and BigQuery
    Reduced alert latency by 40 percent

    SKILLS
    Python FastAPI Docker Kubernetes AWS PostgreSQL Redis
    """ * 3  # repeat to hit word count

    passed, reason = run_filters(good_text)
    print(f"Good resume  : {'PASSED' if passed else 'FAILED'} — {reason}")

    # Test 2 — empty text
    passed, reason = run_filters("")
    print(f"Empty text   : {'PASSED' if passed else 'FAILED'} — {reason}")

    # Test 3 — too short
    passed, reason = run_filters("John Doe Python Developer")
    print(f"Too short    : {'PASSED' if passed else 'FAILED'} — {reason}")

    # Test 4 — no sections
    passed, reason = run_filters(
        "lorem ipsum dolor sit amet consectetur adipiscing elit " * 30
    )
    print(f"No sections  : {'PASSED' if passed else 'FAILED'} — {reason}")




