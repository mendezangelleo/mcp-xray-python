# tests/test_llm.py
import sys
import os
import pytest

# Add 'src' to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.llm import llm_compare_and_sync
# We need these helpers from gherkin to create signatures
from core.gherkin import make_signature, sanitize_title

# --- Helper data for tests ---
ISSUE_KEY = "TEST-1"
SUMMARY = "Test Sync Logic"

def _mock_test(key: str, title: str, steps: str) -> dict:
    """Creates a mock existing test object."""
    norm_title = sanitize_title(ISSUE_KEY, title)
    return {
        "key": key,
        "summary": f"{ISSUE_KEY} | {title}",
        "norm_title": norm_title,
        "gherkin": steps,
        "signature": make_signature(norm_title, steps)
    }

def _mock_scenario(title: str, steps: str) -> dict:
    """Creates a mock new scenario object from the AI."""
    return {"title": title, "steps": steps}

# --- Test Cases ---

def test_sync_creates_new_scenarios():
    """Tests that new scenarios are added to the 'to_create' list."""
    existing_tests = []
    new_scenarios = [
        _mock_scenario("Validate Login", "Given...")
    ]
    plan = llm_compare_and_sync(ISSUE_KEY, SUMMARY, existing_tests, new_scenarios)
    
    assert len(plan["to_create"]) == 1
    assert len(plan["to_update"]) == 0
    assert len(plan["obsolete"]) == 0
    assert plan["to_create"][0]["title"] == "Validate Login"

def test_sync_finds_no_changes():
    """Tests that identical tests are ignored (no create, update, or obsolete)."""
    existing_tests = [
        _mock_test("TEST-2", "Validate Login", "Given...")
    ]
    new_scenarios = [
        _mock_scenario("Validate Login", "Given...")
    ]
    plan = llm_compare_and_sync(ISSUE_KEY, SUMMARY, existing_tests, new_scenarios)

    assert len(plan["to_create"]) == 0
    assert len(plan["to_update"]) == 0
    assert len(plan["obsolete"]) == 0

def test_sync_finds_updates():
    """Tests that a changed scenario is added to the 'to_update' list."""
    existing_tests = [
        _mock_test("TEST-2", "Validate Login", "Given... old step")
    ]
    new_scenarios = [
        _mock_scenario("Validate Login", "Given... new step") # Steps changed
    ]
    plan = llm_compare_and_sync(ISSUE_KEY, SUMMARY, existing_tests, new_scenarios)

    assert len(plan["to_create"]) == 0
    assert len(plan["to_update"]) == 1
    assert len(plan["obsolete"]) == 0
    assert plan["to_update"][0]["key"] == "TEST-2"
    assert plan["to_update"][0]["steps"] == "Given... new step"

def test_sync_finds_obsolete_tests():
    """Tests that an existing test not in the AI list is marked 'obsolete'."""
    existing_tests = [
        _mock_test("TEST-2", "Validate Login", "Given...")
    ]
    new_scenarios = [] # AI returned no tests
    
    plan = llm_compare_and_sync(ISSUE_KEY, SUMMARY, existing_tests, new_scenarios)

    assert len(plan["to_create"]) == 0
    assert len(plan["to_update"]) == 0
    assert len(plan["obsolete"]) == 1
    assert plan["obsolete"][0]["key"] == "TEST-2"

def test_sync_complex_mixture():
    """Tests a mix of create, update, and obsolete."""
    existing_tests = [
        _mock_test("TEST-2", "Validate Login", "Given... old step"), # This will be updated
        _mock_test("TEST-3", "Validate Logout", "Given... logout")   # This is obsolete
    ]
    new_scenarios = [
        _mock_scenario("Validate Login", "Given... new step"),        # Updated version of TEST-2
        _mock_scenario("Validate Password Reset", "Given... reset") # This is new
    ]
    
    plan = llm_compare_and_sync(ISSUE_KEY, SUMMARY, existing_tests, new_scenarios)

    assert len(plan["to_create"]) == 1
    assert len(plan["to_update"]) == 1
    assert len(plan["obsolete"]) == 1
    assert plan["to_create"][0]["title"] == "Validate Password Reset"
    assert plan["to_update"][0]["key"] == "TEST-2"
    assert plan["obsolete"][0]["key"] == "TEST-3"