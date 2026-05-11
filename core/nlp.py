from core.extractor import extract_resume_text
from core.cleaner import fix_layer1
from core.cleaner import fix_layer2
from core.cleaner import fix_sections
import spacy
from pathlib import Path



# batch loading
def load_all_resumes(folder_path:str)->list:
    folder = Path(folder_path)
    pdf_files = list(folder.glob("*.pdf"))
    resumes=[]
    for pdf_file in pdf_files:
        try:
            text = extract_resume_text(str(pdf_file))
            text = fix_layer1(text)
            text = fix_layer2(text)
            text = fix_sections(text)

            top_text = "\n".join(text[:10])
            name=None
            nlp = spacy.load("en_core_web_sm")
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_=="PERSON":
                    name=ent.text

            resumes.append({
                "candidate_name":name,
                "resume_text":text,
                "file":pdf_file.name
            })
            print(f"Loaded:{pdf_file.name}")
        except Exception as e:
            print(f"Failed:{pdf_file.name}")
    return resumes