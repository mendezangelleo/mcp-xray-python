# tests/test_adf.py
import sys
import os
import pytest

# Add 'src' to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.adf import adf_to_text, plain_to_adf, adf_with_code_block, adf_extract_codeblocks

def test_plain_to_adf():
    """Tests converting plain text to ADF JSON."""
    text = "Hello\nWorld"
    expected_adf = {
        "type": "doc", "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "World"}]}
        ]
    }
    assert plain_to_adf(text) == expected_adf

def test_adf_with_code_block():
    """Tests creating an ADF doc with a Gherkin code block."""
    adf = adf_with_code_block("My Title", "Given...")
    assert adf["content"][0]["type"] == "heading"
    assert adf["content"][0]["content"][0]["text"] == "My Title"
    assert adf["content"][1]["type"] == "codeBlock"
    assert adf["content"][1]["attrs"]["language"] == "gherkin"
    assert adf["content"][1]["content"][0]["text"] == "Given..."

def test_adf_to_text_simple():
    """Tests converting simple ADF to plain text."""
    adf = plain_to_adf("Hello World")
    assert adf_to_text(adf) == "Hello World"

def test_adf_extract_codeblocks():
    """Tests extracting Gherkin code blocks from ADF."""
    adf = adf_with_code_block("Test Steps", "Given a user\nWhen...")
    
    # Add another paragraph
    adf["content"].append({"type": "paragraph", "content": [{"type": "text", "text": "Some other text"}]})
    
    blocks = adf_extract_codeblocks(adf)
    assert len(blocks) == 1
    assert blocks[0] == "Given a user\nWhen..."