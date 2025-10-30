# src/jt/__init__.py

# --- Imports ---
import logging
import os
import time
import uuid
from typing import Any, Dict, List

# Capa core
from core import adf as A
from core import dedupe as D
from core import gherkin as G
from core import jira as J
from core import llm as L
from core.config import DEFAULT_PROJECT_KEY, RELATES_LINK_TYPE

log = logging.getLogger(__name__)

# --- Constantes de configuración ---
MAX_CONTEXT_CHARS = int(os.getenv("LLM_MAX_CONTEXT_CHARS", "16000"))
MAX_COMMENTS = int(os.getenv("LLM_MAX_COMMENTS", "10"))
MAX_COMMENT_CHARS = int(os.getenv("LLM_MAX_COMMENT_CHARS", "600"))

# --- Helper para formatear comentarios ---
def format_and_filter_comments(comments_data: list) -> str:
    if not comments_data:
        return "No additional comments."
    formatted_comments: List[str] = []
    noise_filter = ("listo", "hecho", "done", "ok", "gracias", "de acuerdo")
    for comment in comments_data[:MAX_COMMENTS]:
        body_raw = comment.get("body", {})
        body_text = A.adf_to_text(body_raw).strip() if isinstance(body_raw, dict) else str(body_raw).strip()
        if not body_text or len(body_text.split()) < 3 or body_text.lower() in noise_filter:
            continue
        if len(body_text) > MAX_COMMENT_CHARS:
            body_text = body_text[:MAX_COMMENT_CHARS] + " [...]"
        author = comment.get("author", {}).get("displayName", "User")
        formatted_comments.append(f"- Comment from {author}: {body_text}")
    return "\n".join(formatted_comments) if formatted_comments else "No relevant comments found."

# --- Registro de Herramientas ---
def register_tools(mcp: Any):

    @mcp.tool()
    def diag_env() -> Dict[str, Any]:
        return {
            "JIRA_BASE": J.JIRA_BASE,
            "GOOGLE_CLOUD_PROJECT_ID": L.PROJECT_ID,
            "status": "ok"
        }

    @mcp.tool()
    def jira_generate_and_dedupe_tests_from_issue(
        issue_key: str,
        target_project_key: str = DEFAULT_PROJECT_KEY,
        link_type: str = "Tests",
        attach_feature: bool = True,
        fill_xray: bool = False,
        max_tests: int = 20,
        prefer: str = "newest",
    ) -> Dict[str, Any]:
        rid = uuid.uuid4().hex[:8]
        t0 = time.time()
        log.info(f"[{rid}] Iniciando refinamiento de la suite de tests para {issue_key}…")

        src = J.get_issue(issue_key)
        if not src.get("ok"):
            return {"ok": False, "error": "Could not read the source issue."}

        summary_src, desc, labels = src["summary"], src["description"], src.get("labels", [])
        comments_data = J.jira_request(f"/rest/api/3/issue/{issue_key}/comment").get("comments", [])
        relevant_comments = format_and_filter_comments(comments_data)
        full_context = (
            f"**USER STORY DESCRIPTION:**\n{desc}\n\n"
            f"**ADDITIONAL COMMENTS & CLARIFICATIONS:**\n{relevant_comments}"
        )
        if len(full_context) > MAX_CONTEXT_CHARS:
            log.info(f"[{rid}] Contexto > {MAX_CONTEXT_CHARS} chars; recortando…")
            full_context = full_context[:MAX_CONTEXT_CHARS] + "\n\n[...truncated by server tool...]"

        labels_lower = [label.lower() for label in labels]
        is_backend_task = ("[be]" in summary_src.lower()) or ("backend" in labels_lower and "frontend" not in labels_lower)
        system_prompt = L.SYS_MSG_GENERATE_API_TESTS if is_backend_task else L.SYS_MSG_GENERATE_SCENARIOS
        extra_labels = ["api-test"] if is_backend_task else []
        log.info(f"[{rid}] Detectada tarea de {'Backend' if is_backend_task else 'BDD/UI'} para {issue_key}.")

        # --- LLAMADA DIRECTA Y SIMPLE A LA IA ---
        try:
            log.info(f"[{rid}] Llamando a llm_generate_scenarios directamente...")
            ideal_scenarios, gen_method = L.llm_generate_scenarios(
                issue_key=issue_key,
                summary=summary_src,
                full_context=full_context,
                max_tests=max_tests,
                system_prompt=system_prompt
            )
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            log.error(f"[{rid}] La llamada directa al LLM falló: {e} (took {elapsed}ms)", exc_info=True)
            return {"ok": False, "error": f"LLM Exception: {e}"}

        if not ideal_scenarios:
            return {"ok": False, "error": f"FALLBACK: {gen_method}"}

        # --- Lógica de Sincronización ---
        log.info(f"[{rid}] Obteniendo tests existentes y creando plan de sync…")
        existing_tests = J.get_existing_tests_with_details(issue_key, target_project_key)
        sync_plan = L.llm_compare_and_sync(issue_key, summary_src, existing_tests, ideal_scenarios)
        created_report, updated_report, obsolete_report = [], [], []

        for item in sync_plan.get("to_update", []):
            J.update_test_issue(item['key'], item['summary'], item['steps'])
            updated_report.append({"key": item['key'], "summary": item['summary']})

        cur_index = J.next_tc_index(issue_key, target_project_key)
        base_labels = ["mcp", "auto-generated"] + extra_labels
        for item in sync_plan.get("to_create", []):
            clean_title = item.get("title", "Untitled Test")
            tc_tag = f"TC{cur_index:02d}"
            test_summary = f"{issue_key} | {tc_tag} | {clean_title}"
            feature_text = G.build_feature_single(summary=summary_src, issue_key=issue_key, sc=item)
            result = _create_and_process_test_case(
                project_key=target_project_key, summary=test_summary, gherkin_text=feature_text,
                source_issue_key=issue_key, description=f"Auto-generated test for {issue_key}.",
                labels=base_labels, link_type=link_type, attach_feature=attach_feature,
                fill_xray=fill_xray, filename=f"{issue_key}-{tc_tag}.feature",
            )
            created_report.append({**result, "tc_tag": tc_tag})
            cur_index += 1

        for test in sync_plan.get("obsolete", []):
            J.add_labels_to_issue(test['key'], ["revisar-obsoleto"])
            obsolete_report.append(test['key'])

        
        dedupe_result = D.dedupe_linked_tests(parent_key=issue_key, project_key=target_project_key, prefer=prefer)
        elapsed = int((time.time() - t0) * 1000)
        log.info(f"[{rid}] Flujo completado en {elapsed}ms. Creados={len(created_report)}; Actualizados={len(updated_report)}; Obsoletos={len(obsolete_report)}; Duplicados eliminados={len(dedupe_result.get('deleted', []))}")

        return {
            "ok": True, "created": created_report, "updated": updated_report,
            "marked_as_obsolete": obsolete_report,
            "duplicates_deleted": dedupe_result.get("deleted", []),
        }

    @mcp.tool()
    def jira_dedupe_tests(issue_key: str, project_key: str = DEFAULT_PROJECT_KEY, prefer: str = "newest") -> Dict[str, Any]:
        result = D.dedupe_linked_tests(issue_key, project_key, prefer=prefer)
        return {"ok": True, **result}

    def _create_and_process_test_case(**kwargs) -> Dict[str, Any]:
        created_issue = J.create_test_issue(
            project_key=kwargs['project_key'], summary=kwargs['summary'],
            description_text=kwargs['description'], gherkin=kwargs['gherkin_text'], labels=kwargs['labels']
        )
        new_key = created_issue["key"]
        try:
            J.link_issues(new_key, kwargs['source_issue_key'], link_type=kwargs['link_type'])
        except Exception:
            J.link_issues(new_key, kwargs['source_issue_key'], link_type=RELATES_LINK_TYPE)
        if kwargs['attach_feature']:
            try: J.attach_feature(new_key, kwargs['gherkin_text'], filename=kwargs['filename'])
            except Exception as e: logging.error(f"Failed to attach feature to {new_key}: {e}")
        if kwargs['fill_xray']:
            try: J.xray_import_feature(kwargs['gherkin_text'], project_key=kwargs['project_key'], test_key=new_key)
            except Exception as e: logging.error(f"Failed to import to Xray for {new_key}: {e}")
        return {"test_key": new_key, "summary": kwargs['summary'], "preview": kwargs['gherkin_text'][:300]}