import pdfplumber

def extract_resume_text(pdf_path):
    texts=[]
    with pdfplumber.open(f"{pdf_path}") as pdf:
        # first_page=pdf.pages[0]
        for page in pdf.pages:
            text=page.extract_text()
            if text:
                texts.append(text)
    all_text="\n".join(texts) # for multiple pages
    return all_text