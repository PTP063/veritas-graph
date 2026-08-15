import pdfplumber
from pydantic import BaseModel


class PhraseGrounding(BaseModel):
    page_num: int
    x0: float
    top: float
    x1: float
    bottom: float


def find_phrase_coordinates(pdf_path: str, phrase: str) -> PhraseGrounding:
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # pdfplumber search function returns dicts of matching boxes
            results = page.search(phrase)
            if results:
                # We expect exactly one occurrence according to our requirements
                result = results[0]
                return PhraseGrounding(
                    page_num=page_idx + 1,
                    x0=float(result["x0"]),
                    top=float(result["top"]),
                    x1=float(result["x1"]),
                    bottom=float(result["bottom"]),
                )

    raise ValueError(f"Phrase '{phrase}' not found in the document.")
