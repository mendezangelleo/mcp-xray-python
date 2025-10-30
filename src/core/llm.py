# src/core/llm.py

import os
import re
import json
import logging
import time
from typing import List, Dict, Tuple, Any, Optional

# SDK de Google Vertex AI
try:
    import vertexai
    from vertexai.generative_models import (
        GenerativeModel,
        HarmCategory,
        HarmBlockThreshold,
        SafetySetting,
    )
    from google.api_core import exceptions as google_exceptions

    PROJECT_ID: Optional[str] = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    LOCATION: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

    if PROJECT_ID:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
except ImportError:
    vertexai = None
    PROJECT_ID = None
    google_exceptions = None

# Módulos Locales
from .gherkin import sanitize_title, make_signature
# Se elimina la importación de imágenes

log = logging.getLogger(__name__)


# --- Prompts Base (sin cambios) ---
SYS_MSG_GENERATE_SCENARIOS = (
    "You are a highly experienced Senior QA Analyst. Your task is to analyze the full context of a user story from Jira and create a comprehensive set of test cases. You must be rigorous and cover all requirements provided.\n\n"
    "**YOUR RULES:**\n"
    "1.  **HOLISTIC ANALYSIS:** You will be given a context with multiple sections like 'Scenarios', 'Copys', and 'Amplitude'. You MUST treat every section as a source of requirements and create test cases for ALL of them. Do not stop after processing only the 'Scenarios' section.\n"
    "2.  **GHERKIN (ENGLISH):** All test cases must be written in Gherkin format, in English, and from a third-person perspective.\n"
    "3.  **REQUIREMENT-DRIVEN TESTS:**\n"
    "    - For each 'Scenario' in the context, create a detailed Gherkin test case that validates it.\n"
    "    - For the 'Copys' table, create **ONLY TWO** consolidated test cases: one for all Spanish texts and one for all English texts.\n"
    "    - For each 'Amplitude' event, create a specific test case to verify the event is triggered correctly.\n"
    "4.  **BE SPECIFIC:** Use concrete actions and verifiable outcomes. Avoid generic steps.\n"
    "5.  **TITLES:** Every scenario title must start with 'Validate' and be descriptive. **Do not just copy the scenario title from the context.**\n"
    "6.  **STRICT JSON OUTPUT:** Your final output must be a SINGLE, valid JSON object with one key: `scenarios`, containing a list of objects with a `title` (string) and `steps` (a single string with newlines `\\n`)."
)

SYS_MSG_GENERATE_API_TESTS = (
    "You are a meticulous QA Engineer specializing in backend and API testing. Your task is to analyze technical requirements and create specific API test cases.\n\n"
    "**YOUR RULES:**\n"
    "1.  **ANALYZE TECHNICAL DETAILS:** Focus on changes to services, endpoints, request bodies, and data structures. If the user provides Gherkin scenarios, adopt them directly. Ignore UI/UX aspects.\n"
    "2.  **API GHERKIN:** Write scenarios in Gherkin format that describe API interactions.\n"
    "3.  **VALIDATE CONTRACTS:** Create tests for changes like adding or deprecating fields.\n"
    "4.  **NEGATIVE PATHS:** Create tests for potential errors.\n"
    "5.  **STRICT JSON OUTPUT:** Your final output must be a SINGLE, valid JSON object with one key: `scenarios`, containing a list of objects with `title` and `steps`."
)


# --- Helpers internos (sin cambios) ---
def _extract_first_json_object(s: str) -> Optional[str]:
    start = s.find("{")
    if start == -1: return None
    depth = 0
    for i, ch in enumerate(s[start:], start=start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: return s[start : i + 1]
    return None


def _response_text(response: Any) -> str:
    """Extrae texto consolidado desde el objeto de respuesta de Gemini."""
    if not response:
        return ""
    text_value = getattr(response, "text", None)
    if isinstance(text_value, str) and text_value.strip():
        return text_value
    collected: List[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                collected.append(part_text)
                continue
            part_dict = None
            if hasattr(part, "as_dict"):
                part_dict = part.as_dict() or None
            elif isinstance(part, dict):
                part_dict = part
            if not part_dict:
                continue
            text_part = part_dict.get("text")
            if isinstance(text_part, str) and text_part.strip():
                collected.append(text_part)
                continue
            json_part = part_dict.get("json")
            if json_part is not None:
                try:
                    collected.append(json.dumps(json_part))
                except TypeError:
                    pass
    if collected:
        return "".join(collected)
    if hasattr(response, "to_dict"):
        as_dict = response.to_dict() or {}
        text_part = as_dict.get("text")
        if isinstance(text_part, str) and text_part.strip():
            return text_part
        for candidate in as_dict.get("candidates", []) or []:
            content = (candidate or {}).get("content") or {}
            for part in content.get("parts", []) or []:
                if not isinstance(part, dict):
                    continue
                text_part = part.get("text")
                if isinstance(text_part, str) and text_part.strip():
                    return text_part
                json_part = part.get("json")
                if json_part is not None:
                    try:
                        return json.dumps(json_part)
                    except TypeError:
                        continue
    return ""


# src/core/llm.py

def llm_generate_scenarios(
    issue_key: str,
    summary: str,
    full_context: str,
    max_tests: int = 15,
    system_prompt: str = SYS_MSG_GENERATE_SCENARIOS,
) -> Tuple[List[Dict[str, str]], str]:

    def fallback(reason: str) -> Tuple[List[Dict[str, str]], str]:
        log.error(f"FALLBACK ACTIVADO para '{summary}': {reason}")
        return [], reason

    if not vertexai or not PROJECT_ID:
        return fallback("Vertex AI SDK o GOOGLE_CLOUD_PROJECT_ID no disponibles.")

    # ---- Configuración y Modelos ----
    TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
    # --- El nombre del modelo ahora se leerá correctamente desde .env ---
    MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-001")
    
    try:
        # --- Construcción del Prompt (solo texto) ---
        prompt_parts: List[str] = [
            f"--- START OF JIRA ISSUE CONTEXT ---\n**USER STORY SUMMARY:** {summary}\n\n{full_context}\n--- END OF JIRA ISSUE CONTEXT ---"
        ]

        # --- INICIO DE LOGS ADICIONALES ---
        log.info(f"Contexto para '{issue_key}' tiene un tamaño de {len(full_context)} caracteres.")
        if len(full_context) > 1000000: # Un umbral de ejemplo, Flash tiene un contexto grande pero es bueno saber si es excesivo
            log.warning("El tamaño del contexto es muy grande, podría causar lentitud o errores.")
        # --- FIN DE LOGS ADICIONALES ---

        generation_config = {
            "response_mime_type": "application/json",
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
            "max_output_tokens": int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048")),
        }
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_NONE),
        ]
        
        # --- Llamada a la API de Gemini ---
        log.info(f"Intentando generar con el modelo '{MODEL_NAME}' (timeout={TIMEOUT}s)...")
        model = GenerativeModel(MODEL_NAME, system_instruction=system_prompt)
        
        call_started = time.time()
        response = model.generate_content(
            prompt_parts,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        elapsed_ms = int((time.time() - call_started) * 1000)

        # --- INICIO DE LOGS ADICIONALES ---
        log.info(f">>> Respuesta recibida de Gemini en {elapsed_ms}ms.")
        raw_text = _response_text(response)
        log.debug(f"Respuesta en crudo de Gemini: {raw_text[:500]}...") # Logueamos los primeros 500 caracteres
        # --- FIN DE LOGS ADICIONALES ---

        # --- Procesamiento de la Respuesta ---
        if not raw_text.strip():
            return fallback("La respuesta de Gemini no incluyó texto utilizable.")

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            candidate = _extract_first_json_object(raw_text)
            if not candidate:
                return fallback(f"La respuesta no era un JSON válido. Contenido: {raw_text[:200]}...")
            data = json.loads(candidate)
        
        scenarios_from_llm = data.get("scenarios") or []
        if not scenarios_from_llm:
            return fallback("El JSON de respuesta no contenía la clave 'scenarios'.")

        processed_scenarios: List[Dict[str, str]] = []
        for sc in scenarios_from_llm[:max_tests]:
            title = (sc.get("title") or "Untitled").strip()
            steps = sc.get("steps")
            steps_str = "\n".join(steps) if isinstance(steps, list) else str(steps or "")
            if title and steps_str:
                processed_scenarios.append({"title": title, "steps": steps_str})

        if not processed_scenarios:
            return fallback("No se encontraron escenarios válidos en la respuesta del modelo.")

        log.info(f"{len(processed_scenarios)} escenarios generados con Gemini.")
        return processed_scenarios, "gemini"

    except (google_exceptions.DeadlineExceeded, google_exceptions.RetryError) as e:
        log.error(f"Timeout o error de reintento con el modelo '{MODEL_NAME}': {e}")
        return fallback(f"La llamada a Gemini superó el tiempo de espera.")
    except Exception as e:
        # --- INICIO DE LOGS ADICIONALES ---
        log.error(f"Error inesperado con el modelo '{MODEL_NAME}': {e}", exc_info=True)
        # Intentamos obtener más detalles del error si están disponibles
        if hasattr(e, 'message'):
            log.error(f"Detalle del error: {e.message}")
        # --- FIN DE LOGS ADICIONALES ---
        return fallback(f"Excepción general: {e}")


# --- La función de sincronización no necesita cambios ---
def llm_compare_and_sync(
    issue_key: str,
    summary: str,
    existing_tests: List[Dict[str, Any]],
    new_scenarios: List[Dict[str, str]],
) -> Dict[str, List[Dict[str, Any]]]:
    # (El resto del archivo no necesita cambios)
    log.info("Sincronizando escenarios generados con tests existentes...")
    to_create: List[Dict[str, str]] = []
    to_update: List[Dict[str, Any]] = []
    existing_map: Dict[str, Dict[str, Any]] = {}
    for test in existing_tests:
        summary_text = test.get("summary", "")
        norm = test.get("norm_title") or sanitize_title(issue_key, summary_text)
        sig = test.get("signature")
        if not sig:
            gherkin = test.get("gherkin", "")
            sig = make_signature(norm, gherkin) if gherkin else make_signature(norm, "")
        test_fixed = {**test, "norm_title": norm, "signature": sig}
        existing_map[norm] = test_fixed
    new_map = {
        sanitize_title(issue_key, sc["title"]): {
            **sc,
            "signature": make_signature(sanitize_title(issue_key, sc["title"]), sc["steps"]),
        }
        for sc in new_scenarios
    }
    for norm_title, new_data in new_map.items():
        if norm_title not in existing_map:
            to_create.append(new_data)
        else:
            existing_test = existing_map[norm_title]
            if new_data["signature"] != existing_test["signature"]:
                summary_parts = existing_test["summary"].split("|")
                if len(summary_parts) > 1:
                    new_summary = f"{summary_parts[0].strip()} | {summary_parts[1].strip()} | {new_data['title']}"
                else:
                    new_summary = f"{issue_key} | {new_data['title']}"
                to_update.append(
                    {
                        "key": existing_test["key"],
                        "summary": new_summary,
                        "steps": new_data["steps"],
                    }
                )
    obsolete = [test for norm_title, test in existing_map.items() if norm_title not in new_map]
    log.info(
        f"Sincronización: {len(to_create)} para crear, {len(to_update)} para actualizar, {len(obsolete)} obsoletos."
    )
    return {"to_create": to_create, "to_update": to_update, "obsolete": obsolete}