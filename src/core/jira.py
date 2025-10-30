# src/core/jira.py
import os
import json
import base64
import re
import time
import logging
from random import random
from typing import Dict, List, Any
from collections import defaultdict

import requests

from .config import JIRA_BASE, JIRA_EMAIL, JIRA_TOKEN, RELATES_LINK_TYPE
from .adf import adf_to_text, adf_with_code_block, plain_to_adf
from .gherkin import make_signature, sanitize_title

log = logging.getLogger(__name__)


def _auth_header() -> str:
    """Construye el header Authorization para Jira (Basic con API token)."""
    return "Basic " + base64.b64encode(
        f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode("utf-8")
    ).decode("utf-8")


def jira_request(
    path: str,
    params: dict = None,
    method: str = "GET",
    body: dict = None
) -> dict:
    """
    Wrapper de requests a Jira Cloud con pequeño backoff para 429/5xx.
    Devuelve {} si no hay cuerpo. Lanza excepción en error definitivo.
    """
    url = f"{JIRA_BASE.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _auth_header(),
    }

    max_retries = int(os.getenv("JIRA_MAX_RETRIES", "3"))
    backoff = float(os.getenv("JIRA_BACKOFF", "0.6"))

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                data=(json.dumps(body) if body else None),
                timeout=30,
            )
            # Retentar en 429/5xx
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.exceptions.RequestException(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
            resp.raise_for_status()
            return resp.json() if resp.status_code != 204 and resp.text else {}
        except requests.exceptions.RequestException as e:
            log.warning(f"Jira request falló (intento {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                log.error(f"Jira API request failed definitivamente: {e}")
                raise
            sleep_for = backoff * attempt + random() * 0.2
            time.sleep(sleep_for)


def get_issue(issue_key: str) -> dict:
    """
    Obtiene los detalles de un issue, incluyendo su descripción y un bloque de texto con comentarios.
    """
    try:
        fields_to_get = "summary,description,labels,issuetype,parent,comment"
        data = jira_request(f"/rest/api/3/issue/{issue_key}", params={"fields": fields_to_get})

        fields = data.get("fields", {}) or {}
        summary = fields.get("summary", "") or ""

        desc_raw = fields.get("description")
        desc_text = adf_to_text(desc_raw) if isinstance(desc_raw, dict) else (desc_raw or "")

        comments_raw = (fields.get("comment") or {}).get("comments", []) or []
        comments_text: List[str] = []
        for comment in comments_raw:
            author = (comment.get("author") or {}).get("displayName", "Unknown")
            body_adf = comment.get("body")
            comment_content = adf_to_text(body_adf) if isinstance(body_adf, dict) else (body_adf or "")
            if comment_content:
                comments_text.append(f"Comment from {author}:\n{comment_content}")

        all_comments_str = "\n\n---\n\n".join(comments_text)
        log.info(f"Leído {issue_key}: '{summary[:50]}...'")

        return {
            "ok": True,
            "key": issue_key,
            "summary": summary,
            "description": desc_text,
            "comments": all_comments_str,
            "full_context": f"DESCRIPTION:\n{desc_text}\n\nCOMMENTS:\n{all_comments_str}",
            "description_adf": desc_raw,
            "labels": fields.get("labels", []) or [],
        }
    except Exception as e:
        log.error(f"No se pudo leer el issue {issue_key}: {e}")
        return {"ok": False, "error": str(e)}


def create_test_issue(
    project_key: str,
    summary: str,
    description_text: str = "",
    gherkin: str = "",
    labels: List[str] = None,
) -> dict:
    adf_desc = adf_with_code_block("Steps (Gherkin)", gherkin) if gherkin else plain_to_adf(description_text)
    body = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": "Test"},
            "labels": labels or ["mcp", "auto-generated"],
            "description": adf_desc,
        }
    }
    data = jira_request("/rest/api/3/issue", method="POST", body=body)
    log.info(f"Creado Test Case: {data['key']}")
    return {"ok": True, "key": data["key"], "self": data.get("self")}


def update_test_issue(issue_key: str, new_summary: str, new_gherkin: str) -> dict:
    log.info(f"Actualizando issue {issue_key} con nuevo título: {new_summary}")
    new_adf_desc = adf_with_code_block("Steps (Gherkin)", new_gherkin)
    body = {"fields": {"summary": new_summary, "description": new_adf_desc}}
    jira_request(f"/rest/api/3/issue/{issue_key}", method="PUT", body=body)
    return {"ok": True, "updated_key": issue_key}


def add_labels_to_issue(issue_key: str, labels_to_add: List[str]) -> dict:
    log.info(f"Añadiendo etiquetas {labels_to_add} a {issue_key}")
    body = {"update": {"labels": [{"add": label} for label in labels_to_add]}}
    jira_request(f"/rest/api/3/issue/{issue_key}", method="PUT", body=body)
    return {"ok": True, "labeled_key": issue_key}


def _get_linked_issue_keys(parent_key: str) -> List[str]:
    try:
        data = jira_request(f"/rest/api/3/issue/{parent_key}", params={"fields": "issuelinks"})
        issue_links = (data.get("fields") or {}).get("issuelinks", []) or []
        linked_keys: List[str] = []
        for link in issue_links:
            if "outwardIssue" in link:
                linked_keys.append(link["outwardIssue"]["key"])
            elif "inwardIssue" in link:
                linked_keys.append(link["inwardIssue"]["key"])
        return linked_keys
    except Exception:
        return []


def get_linked_test_issues(parent_key: str, project_key: str) -> List[Dict[str, Any]]:
    linked_keys = _get_linked_issue_keys(parent_key)
    if not linked_keys:
        return []
    jql = f'key in ({",".join(linked_keys)}) AND project = "{project_key}" AND issuetype = "Test"'
    fields = "summary,created,description"
    data = jira_request("/rest/api/3/search/jql", params={"jql": jql, "fields": fields, "maxResults": 100})
    return data.get("issues", []) or []


def next_tc_index(parent_key: str, project_key: str) -> int:
    issues = get_linked_test_issues(parent_key, project_key)
    max_tc = 0
    for issue in issues:
        summary = (issue.get("fields") or {}).get("summary", "") or ""
        match = re.search(r"TC(\d+)", summary, re.IGNORECASE)
        if match:
            max_tc = max(max_tc, int(match.group(1)))
    return max_tc + 1


def get_existing_tests_with_details(issue_key: str, project_key: str) -> List[Dict[str, Any]]:
    log.info(f"Buscando tests existentes con detalles para {issue_key}...")
    linked_keys = _get_linked_issue_keys(issue_key)
    if not linked_keys:
        log.info(f"No se encontraron tests existentes para {issue_key}.")
        return []
    try:
        jql = f'key in ({",".join(linked_keys)}) AND issuetype = "Test"'
        fields = "summary,description"
        data = jira_request("/rest/api/3/search/jql", params={"jql": jql, "fields": fields, "maxResults": 100})
        tests_with_details: List[Dict[str, Any]] = []
        for issue in data.get("issues", []) or []:
            issue_fields = issue.get("fields") or {}
            summary = issue_fields.get("summary", "") or ""
            description_adf = issue_fields.get("description")
            gherkin_content = adf_to_text(description_adf) if isinstance(description_adf, dict) else (description_adf or "")
            norm = sanitize_title(issue_key, summary)
            tests_with_details.append({
                "key": issue.get("key"),
                "summary": summary,
                "gherkin": gherkin_content,
                "signature": make_signature(norm, gherkin_content),
                "norm_title": norm,
            })
        log.info(f"Se encontraron {len(tests_with_details)} tests existentes para {issue_key}.")
        return tests_with_details
    except Exception as e:
        log.error(f"Error al obtener los detalles de los tests existentes para {issue_key}: {e}")
        return []


def link_issues(from_issue_key: str, to_issue_key: str, link_type: str = None) -> dict:
    link_name = (link_type or RELATES_LINK_TYPE) or "Relates"
    log.info(f"Enlazando {from_issue_key} -> {to_issue_key} con link_type={link_name}...")
    try:
        body = {
            "type": {"id": "10007"},
            "inwardIssue": {"key": from_issue_key},
            "outwardIssue": {"key": to_issue_key},
        }
        jira_request("/rest/api/3/issueLink", method="POST", body=body)
        log.info("Enlace creado correctamente.")
        return {"ok": True}
    except Exception as e:
        log.error(f"No se pudo crear el enlace entre {from_issue_key} y {to_issue_key}: {e}")
        return {"ok": False, "error": str(e)}


def delete_issue(issue_key: str) -> dict:
    log.warning(f"Eliminando issue duplicado: {issue_key}")
    try:
        jira_request(f"/rest/api/3/issue/{issue_key}", method="DELETE")
        return {"ok": True, "deleted_key": issue_key}
    except Exception as e:
        log.error(f"No se pudo eliminar el issue {issue_key}: {e}")
        return {"ok": False, "error": str(e)}


def dedupe_linked_tests(parent_key: str, project_key: str) -> dict:
    log.info(f"Buscando duplicados para {parent_key}...")
    tests = get_linked_test_issues(parent_key, project_key)

    signatures = defaultdict(list)
    for test in tests:
        key = test.get("key")
        summary = (test.get("fields") or {}).get("summary", "") or ""
        norm_title = sanitize_title(parent_key, summary)
        signatures[norm_title].append({"key": key, "created": (test.get("fields") or {}).get("created")})

    deleted_count = 0
    for norm_title, duplicates in signatures.items():
        if len(duplicates) > 1:
            duplicates.sort(key=lambda x: x["created"], reverse=True)
            for i in range(1, len(duplicates)):
                issue_to_delete = duplicates[i]["key"]
                delete_issue(issue_to_delete)
                deleted_count += 1

    log.info(f"Proceso de deduplicación completado. {deleted_count} tests eliminados.")
    return {"ok": True, "deleted_count": deleted_count}


def attach_feature(issue_key: str, feature: str, filename: str = None) -> dict:
    log.info(
        f"Placeholder: Se intentó adjuntar la feature '{filename or 'feature.txt'}' "
        f"a {issue_key}. (No se realizó ninguna acción)."
    )
    return {"ok": True}