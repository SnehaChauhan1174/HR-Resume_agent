from core.extractor import extract_resume_text
from core.cleaner import fix_layer1, fix_layer2, fix_sections
from core.extract_structure import extract_structured_resume
from core.filter import run_filters
from parsers.jd_parser import parse_jd

#Main pipeline
def run_pipeline():

    pdf_path = "../resumes/Ria_Bishnoi_resume.pdf"

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



        # ── Stage B: LLM structured extraction ───
    res = extract_structured_resume(cleaned_text, "ria beishnoi")
    print(res.resume)



# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_pipeline()