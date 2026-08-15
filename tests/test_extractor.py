import os
import tempfile
from src.pdf_generator import generate_mock_pdf
from src.extractor import find_phrase_coordinates, PhraseGrounding

def test_find_change_of_control():
    # Use a temporary file for the PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        
    try:
        # Generate the 2-page PDF
        generate_mock_pdf(pdf_path)
        
        # Search for the phrase
        phrase = "Change of Control"
        result = find_phrase_coordinates(pdf_path, phrase)
        
        # Verify the result
        assert isinstance(result, PhraseGrounding)
        assert result.page_num == 2
        
        # Verify coordinates are valid floats and make sense
        assert isinstance(result.x0, float)
        assert isinstance(result.top, float)
        assert isinstance(result.x1, float)
        assert isinstance(result.bottom, float)
        
        assert result.x0 < result.x1
        assert result.top < result.bottom
        
    finally:
        # Clean up
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
