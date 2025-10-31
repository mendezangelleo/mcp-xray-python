# src/core/dedupe.py
from __future__ import annotations
import re, hashlib, logging
from typing import List, Dict, Set, Tuple

from . import jira as J
from . import adf as A
from . import gherkin as G

log = logging.getLogger(__name__)

# ------------------------
# Normalization / signatures
# ------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def make_signature(title_norm: str, feature_text: str) -> str:
    """
    Stable signature: NORMALIZED title + gherkin (normalized).
    Must match the one we use when creating/reading tests.
    """
    payload = f"{_norm(title_norm)}|{_norm(feature_text)}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()

# ------------------------
# Reading linked tests
# ------------------------
def _group_linked_tests_by_signature(parent_key: str, project_key: str) -> Dict[str, List[Dict]]:
    """
    Reads all Tests linked to the parent and groups them by signature.
    Returns {signature: [ {key, created, norm_title, feature, summary}, ... ] }
    """
    buckets: Dict[str, List[Dict]] = {}
    for t in J.get_linked_test_issues(parent_key, project_key):
        full = (t.get("fields") or {}).get("summary", "")
        parts = [p.strip() for p in full.split("|")]
        raw_title = parts[-1] if parts else full                      # right of the last "|"
        norm_title = G.sanitize_title(parent_key, raw_title)          # "Validate …" without prefixes

        description_adf = (t.get("fields") or {}).get("description")
        blocks = A.adf_extract_codeblocks(description_adf)
        feature = "\n".join(blocks) if blocks else ""

        sig = make_signature(norm_title, feature)
        entry = {
            "key": t["key"],
            "created": (t.get("fields") or {}).get("created") or "",
            "norm_title": norm_title,
            "feature": feature,
            "summary": full,
            "signature": sig,
        }
        buckets.setdefault(sig, []).append(entry)
    return buckets

# ------------------------
# Dedupe in-Jira
# ------------------------
def find_duplicates(parent_key: str, project_key: str, prefer: str = "newest") -> Tuple[List[Dict], List[Dict]]:
    """
    Returns (keep, drop) as lists of Test items.
    prefer: "newest" (default) or "oldest" to decide which one to keep.
    """
    keep, drop = [], []
    buckets = _group_linked_tests_by_signature(parent_key, project_key)

    for sig, items in buckets.items():
        if len(items) == 1:
            keep.append(items[0]); continue
        # sort by creation date
        items_sorted = sorted(items, key=lambda x: x["created"] or "")
        if prefer == "oldest":
            keep_item = items_sorted[0]; to_drop = items_sorted[1:]
        else:
            keep_item = items_sorted[-1]; to_drop = items_sorted[:-1]
        keep.append(keep_item); drop.extend(to_drop)
    return keep, drop

def delete_issues(keys: List[str]) -> List[str]:
    deleted: List[str] = []
    for k in keys:
        try:
            J.delete_issue(k)
            deleted.append(k)
        except Exception as e:
            log.warning(f"Could not delete {k}: {e}")
    return deleted

def dedupe_linked_tests(parent_key: str, project_key: str, prefer: str = "newest") -> Dict:
    """
    Finds duplicates among the Tests linked to the parent and DELETES the extras.
    """
    keep, drop = find_duplicates(parent_key, project_key, prefer=prefer)
    deleted = delete_issues([d["key"] for d in drop])
    return {
        "kept":   [k["key"] for k in keep],
        "dropped": [d["key"] for d in drop],
        "deleted": deleted,
    }


def normalize_text(s: str) -> str:
    return _norm(s)

def make_test_signature(test: Dict[str, str]) -> str:
    title = _norm(test.get("title", ""))
    steps = _norm(test.get("steps", ""))
    return hashlib.sha1(f"{title}|{steps}".encode("utf-8")).hexdigest()

def dedupe_tests(tests: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for t in tests:
        sig = make_test_signature(t)
        if sig in seen: 
            continue
        seen.add(sig); out.append(t)
    return out