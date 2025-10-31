# src/core/adf.py
import re
from typing import Any, List, Dict

def adf_to_text(adf: dict) -> str:
    parts: List[str] = []
    def walk(node: Any):
        if not isinstance(node, dict): return
        t = node.get("type"); 
        if not t: return
        if t in ("doc","blockquote","panel"):
            for c in node.get("content", []): walk(c)
        elif t in ("paragraph","heading"):
            line=[]
            for c in node.get("content", []):
                if isinstance(c, dict) and c.get("type")=="text":
                    line.append(c.get("text",""))
                elif isinstance(c, dict) and c.get("type")=="hardBreak":
                    line.append("\n")
            parts.append("".join(line).strip())
        elif t in ("bulletList","orderedList"):
            for li in node.get("content", []):
                if li.get("type")=="listItem":
                    for c in li.get("content", []):
                        if c.get("type")=="paragraph":
                            seg=[]
                            for cc in c.get("content", []):
                                if cc.get("type")=="text":
                                    seg.append(cc.get("text",""))
                            if seg: parts.append("- " + "".join(seg).strip())
                        else:
                            walk(c)
        else:
            for c in node.get("content", []): walk(c)
    walk(adf or {})
    txt = "\n".join([p for p in parts if p])
    return "\n".join([line.rstrip() for line in txt.splitlines()]).strip()

def _adf_collect_text(node: dict) -> str:
    out = []
    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                out.append(n.get("text",""))
            for c in n.get("content",[]) or []:
                walk(c)
        elif isinstance(n, list):
            for x in n: walk(x)
    walk(node)
    return "".join(out).strip()

def extract_tables_from_adf(adf: dict) -> List[List[List[str]]]:
    tables = []
    if not (isinstance(adf, dict) and adf.get("type") == "doc"): return tables
    def walk(n):
        if not isinstance(n, dict): return
        if n.get("type") == "table":
            rows = []
            for r in n.get("content",[]) or []:
                if (r or {}).get("type") != "tableRow": continue
                cells = []
                for c in r.get("content",[]) or []:
                    cells.append(_adf_collect_text(c))
                rows.append(cells)
            if rows: tables.append(rows)
        for c in n.get("content",[]) or []:
            walk(c)
    walk(adf)
    return tables

def adf_collect_links(adf: dict) -> List[str]:
    links = []
    def walk(n):
        if isinstance(n, dict):
            for m in n.get("marks") or []:
                if m.get("type") == "link":
                    href = (m.get("attrs") or {}).get("href")
                    if href: links.append(href)
            for c in n.get("content",[]) or []:
                walk(c)
        elif isinstance(n, list):
            for x in n: walk(x)
    walk(adf or {})
    # unique
    return list(dict.fromkeys(links))

def adf_has_media(adf: dict) -> bool:
    hit = False
    def walk(n):
        nonlocal hit
        if hit: return
        if isinstance(n, dict) and n.get("type") in ("media","mediaSingle"):
            hit = True; return
        for c in n.get("content",[]) or []:
            walk(c)
    walk(adf or {})
    return hit

def plain_to_adf(text: str) -> dict:
    content = []
    for line in (text or "").splitlines():
        if line.strip():
            content.append({"type":"paragraph","content":[{"type":"text","text":line}]})
        else:
            content.append({"type":"paragraph"})
    if not content:
        content=[{"type":"paragraph"}]
    return {"type":"doc","version":1,"content":content}

def adf_with_code_block(title: str, code_text: str) -> dict:
    blocks = []
    if title:
        blocks.append({"type":"heading","attrs":{"level":3},"content":[{"type":"text","text":title}]})
    blocks.append({"type":"codeBlock","attrs":{"language":"gherkin"},
                   "content":[{"type":"text","text":code_text}]})
    return {"type":"doc","version":1,"content":blocks}

def adf_extract_codeblocks(adf: dict, lang: str = "gherkin") -> list[str]:
    blocks = []
    def walk(n):
        if not isinstance(n, dict): return
        if n.get("type") == "codeBlock":
            a = n.get("attrs") or {}
            if not lang or a.get("language") == lang:
                text = []
                for c in n.get("content", []) or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text.append(c.get("text", "")) 
                blocks.append("".join(text))
        for c in n.get("content", []) or []:
            walk(c)
    walk(adf or {})
    return blocks

def dedupe_tests(tests: List[dict]) -> List[dict]:
    """
    Removes duplicate tests based on steps.
    """
    seen = set()
    deduped = []
    for test in tests:
        key = (test.get("title", ""), test.get("steps", ""))
        if key not in seen:
            deduped.append(test)
            seen.add(key)
    return deduped

def build_copy_scenarios(items):
    """Generates ES/EN scenarios from parsed copy rows and removes duplicates."""
    scenarios = []
    for it in items:
        item = it["item"]
        if it.get("es"):
            scenarios.append({
                "title": f"Validate copy - {item} (ES)",
                "steps": "\n".join([
                    "Given the Charge modal is open",
                    "And the application language is Spanish",
                    f"When the UI renders the '{item}' section",
                    f'Then the text equals "{it["es"]}"'
                ])
            })
        if it.get("en"):
            scenarios.append({
                "title": f"Validate copy - {item} (EN)",
                "steps": "\n".join([
                    "Given the Charge modal is open",
                    "And the application language is English",
                    f"When the UI renders the '{item}' section",
                    f'Then the text equals "{it["en"]}"'
                ])
            })
    return dedupe_tests(scenarios)