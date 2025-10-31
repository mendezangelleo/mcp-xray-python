# src/core/gherkin.py
import re
import hashlib
from typing import Dict, List

def sanitize_title(issue_key: str, raw: str) -> str:
    t = (raw or "").strip()
    prefix_pat = rf"^\s*(?:{re.escape(issue_key)}\s*\|\s*)?(?:TC\d+\s*\|\s*)?"
    t = re.sub(prefix_pat, "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(Validate\s*)+", "", t, flags=re.IGNORECASE)
    t = t.strip(" -:–—")
    t = re.sub(r"\s+", " ", t).strip()
    if not t: t = "Untitled Scenario"
    return f"Validate {t}"

def build_feature_single(summary: str, issue_key: str, sc: Dict[str,str]) -> str:
    """
    Builds the .feature file text for a single scenario.
    """
    title = sc.get('title', 'Untitled Scenario')
    # Sanitize the title within the scenario to remove "Validate"
    scenario_title = title.replace("Validate ", "", 1)
    
    steps = sc.get('steps', '# No steps defined')
    
    body = [
        f"@{issue_key}",
        f"Feature: {summary}",
        f"  # Source: {issue_key}",
        "",
        f"  Scenario: {scenario_title}"
    ]
    for line in steps.splitlines():
        body.append(f"    {line.strip()}")
    body.append("")
    return "\n".join(body)

def _norm_gherkin(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def make_signature(title: str, feature_text: str) -> str:
    payload = (_norm_gherkin(title) + "|" + _norm_gherkin(feature_text)).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()

def steps_signature(steps: str) -> str:
    """Signature based only on steps (useful for comparing content)."""
    STEP_RX = re.compile(r"^\s*(Given|When|Then|And|But)\b", re.IGNORECASE)
    lines = []
    for raw in (steps or "").splitlines():
        if STEP_RX.match(raw):
            lines.append(raw.strip().lower())
    if not lines:
        return ""
    t = " | ".join(lines)
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^a-z#\s|]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.md5(t.encode("utf-8")).hexdigest()