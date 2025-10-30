# run_mcp.py (Versión Final Simplificada)
import os
import sys
import logging
import json
import argparse
from dotenv import load_dotenv

# --- PASO 1: Configurar el entorno y el path ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
load_dotenv()
os.environ.setdefault("GOOGLE_CLOUD_DISABLE_GRPC", "true")

# Configuramos un logging para verlo todo en la consola
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("mcp_runner")

# --- PASO 2: Importar la lógica principal ---
try:
    from jt import register_tools
    import vertexai
except ImportError as e:
    log.error(f"No se pudo importar un módulo. Asegúrate de que la estructura de carpetas es correcta. Error: {e}")
    exit()

# --- PASO 3: Simular el 'registro' para obtener la herramienta ---
class FakeMCP:
    def tool(self):
        def decorator(func):
            setattr(self, func.__name__, func)
            return func
        return decorator

# --- La función principal ahora es NORMAL (sin 'async') ---
def main(issue_key: str, project_key: str):
    """
    Función principal que ejecuta todo el flujo en un solo proceso.
    """
    log.info("--- INICIANDO EJECUCIÓN EN MODO UNIFICADO ---")

    try:
        # --- Inicializar dependencias ---
        PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        if not PROJECT_ID:
            raise RuntimeError("ERROR CRÍTICO: Falta GOOGLE_CLOUD_PROJECT_ID en .env")
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        log.info("Vertex AI inicializado.")

        # Obtenemos la función de la herramienta
        mcp_stub = FakeMCP()
        register_tools(mcp_stub)
        if not hasattr(mcp_stub, 'jira_generate_and_dedupe_tests_from_issue'):
            raise RuntimeError("No se pudo obtener la función de la herramienta después de registrarla.")
        
        # Preparamos los parámetros
        payload = {
            "issue_key": issue_key,
            "target_project_key": project_key,
            "link_type": "Tests",
            "attach_feature": True,
            "fill_xray": False,
            "max_tests": 50,
            "prefer": "newest",
        }
        log.info(f"Ejecutando la herramienta con el payload: \n{json.dumps(payload, indent=2)}")
        
        # --- Ejecutar la herramienta (SIN 'await') ---
        result = mcp_stub.jira_generate_and_dedupe_tests_from_issue(**payload)

        # --- Mostrar el resultado ---
        print("\n" + "="*50)
        log.info("¡PROCESO COMPLETADO!")
        if result and result.get("ok"):
            log.info("La herramienta reportó ÉXITO.")
        else:
            log.warning("La herramienta reportó un FALLO.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("="*50 + "\n")

    except Exception as e:
        log.error("❌ La ejecución falló con una excepción inesperada.", exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Herramienta unificada para generar tests en Jira con IA")
    parser.add_argument("--issue", required=True, help="Issue key de Jira (ej: ALL-7638)")
    parser.add_argument("--project", default="ALL", help="Project key de Jira por defecto")
    args = parser.parse_args()
    
    # --- Llamamos a la función directamente (sin 'asyncio.run') ---
    main(args.issue, args.project)