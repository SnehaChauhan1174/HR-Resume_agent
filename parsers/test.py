from pathlib import Path

pdf_files=list(Path("../resumes/").glob("*.pdf"))
print(pdf_files)

for i, pdf_path in enumerate(pdf_files, 1):

    print(f"  [{i}/{len(pdf_files)}] {pdf_path.name}")