import sys
from PyPDF2 import PdfReader

def extract(pdf_path, txt_path):
    print(f"Reading {pdf_path}...")
    try:
        reader = PdfReader(pdf_path)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract("d:/pratik/New folder/Guidelines_English Training.docx.pdf", "d:/pratik/New folder/english_guidelines.txt")
    extract("d:/pratik/New folder/Annotation_Doc_Hindi_Guideline_2026 1.pdf", "d:/pratik/New folder/hindi_guidelines.txt")
