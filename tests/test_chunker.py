from src.chunker import LegalChunker

def test_mechanical_split_fallback():
    chunker = LegalChunker()
    # Create a string of 20000 characters without any headers
    long_text = "A" * 20000
    chunks, is_unstruct = chunker.chunk(long_text)
    
    # 20000 chars divided by (8000 - 200 overlap = 7800 jump)
    # chunk 1: 0 to 8000
    # chunk 2: 7800 to 15800
    # chunk 3: 15600 to 20000 (length 4400)
    assert len(chunks) == 3
    assert len(chunks[0]) == 8000
    assert len(chunks[1]) == 8000
    assert len(chunks[2]) == 4400
    
    # Verify overlap
    assert chunks[0][-200:] == chunks[1][:200]
