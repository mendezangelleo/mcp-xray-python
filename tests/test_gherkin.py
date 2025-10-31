# tests/test_gherkin.py
import sys
import os
import pytest

# Add 'src' to the path so Python can find the 'core' module
# This assumes pytest is run from the project's root folder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# --- Importamos AMBAS funciones que vamos a probar ---
from core.gherkin import sanitize_title, build_feature_single

# --- Tests para sanitize_title (LOS QUE YA TENÍAS) ---
@pytest.mark.parametrize("issue_key, raw_title, expected_output", [
    # Standard cases
    ("PROJ-123", "PROJ-123 | TC01 | Validate Login", "Validate Login"),
    ("PROJ-123", "  PROJ-123 | Validate Login  ", "Validate Login"),
    ("PROJ-123", "TC01 | Validate Login", "Validate Login"),
    ("PROJ-123", "PROJ-123 | Validate Login", "Validate Login"),
    
    # Cases with duplicate "Validate"
    ("PROJ-123", "Validate Validate Login", "Validate Login"),
    ("PROJ-123", "validate validate login", "Validate login"),
    
    # Cases with extra characters
    ("PROJ-123", "  Validate Login -", "Validate Login"),
    ("PROJ-123", "Validate Login :", "Validate Login"),
    ("PROJ-123", "   My Simple Title   ", "Validate My Simple Title"),
    
    # Empty or real title-less cases
    ("PROJ-123", "PROJ-123 | TC01 |", "Validate Untitled Scenario"),
    ("PROJ-123", "   ", "Validate Untitled Scenario"),
    ("PROJ-123", None, "Validate Untitled Scenario"),
    ("PROJ-123", "PROJ-123 |", "Validate Untitled Scenario"),
])
def test_sanitize_title(issue_key, raw_title, expected_output):
    """Tests the title sanitization function."""
    assert sanitize_title(issue_key, raw_title) == expected_output


def test_build_feature_single():
    """Tests that the .feature file content is built correctly."""
    summary = "User Story Summary"
    issue_key = "PROJ-100"
    scenario = {
        "title": "Validate successful login",
        "steps": "Given I am on the login page\nWhen I enter valid credentials\nThen I am logged in"
    }
    
    expected_feature_text = """
@PROJ-100
Feature: User Story Summary
  # Source: PROJ-100

  Scenario: successful login
    Given I am on the login page
    When I enter valid credentials
    Then I am logged in
"""
    
    # We strip both to avoid issues with leading/trailing whitespace
    generated_text = build_feature_single(summary, issue_key, scenario)
    assert generated_text.strip() == expected_feature_text.strip()