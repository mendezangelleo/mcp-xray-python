# run_mcp.py (Updated version)
import os
import sys
import logging
import json
import argparse
from dotenv import load_dotenv

# --- STEP 1: Configure environment and path ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
load_dotenv()
os.environ.setdefault("GOOGLE_CLOUD_DISABLE_GRPC", "true")

# Configure logging to see everything in the console
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("mcp_runner")

# --- STEP 2: Import main logic ---
try:
    from jt import register_tools
    import vertexai
except ImportError as e:
    log.error(f"Could not import a module. Ensure the folder structure is correct. Error: {e}")
    exit()

# --- STEP 3: Simulate 'registration' to get the tool ---
class FakeMCP:
    def tool(self):
        def decorator(func):
            setattr(self, func.__name__, func)
            return func
        return decorator

# --- The main function is now NORMAL (not 'async') ---
def main(issue_key: str, project_key: str, delete_obsolete: bool):
    """
    Main function that runs the entire flow in a single process.
    """
    log.info("--- STARTING EXECUTION IN UNIFIED MODE ---")

    try:
        # --- Initialize dependencies ---
        PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        if not PROJECT_ID:
            raise RuntimeError("CRITICAL ERROR: GOOGLE_CLOUD_PROJECT_ID missing in .env")
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        log.info("Vertex AI initialized.")

        # Get the tool function
        mcp_stub = FakeMCP()
        register_tools(mcp_stub)
        if not hasattr(mcp_stub, 'jira_generate_and_dedupe_tests_from_issue'):
            raise RuntimeError("Could not get the tool function after registering it.")
        
        # Prepare the payload
        payload = {
            "issue_key": issue_key,
            "target_project_key": project_key,
            "link_type": "Tests",
            "attach_feature": True,
            "fill_xray": False,
            "max_tests": 50,
            "prefer": "newest",
            "delete_obsolete": delete_obsolete  # <-- HERE WE ADD THE NEW OPTION
        }
        log.info(f"Executing tool with payload: \n{json.dumps(payload, indent=2)}")
        
        # --- Execute the tool (NO 'await') ---
        result = mcp_stub.jira_generate_and_dedupe_tests_from_issue(**payload)

        # --- Show the result ---
        print("\n" + "="*50)
        log.info("PROCESS COMPLETED!")
        if result and result.get("ok"):
            log.info("Tool reported SUCCESS.")
        else:
            log.warning("Tool reported FAILURE.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("="*50 + "\n")

    except Exception as e:
        log.error("❌ Execution failed with an unexpected exception.", exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified tool to generate Jira tests with AI")
    parser.add_argument("--issue", required=True, help="Jira issue key (e.g., ALL-7638)")
    parser.add_argument("--project", default="ALL", help="Default Jira project key")
    # --- ADDING THE NEW ARGUMENT HERE ---
    parser.add_argument(
        "--delete-obsolete",
        action="store_true",
        help="Instead of tagging, delete obsolete tests."
    )
    args = parser.parse_args()
    
    # --- Call the function directly (no 'asyncio.run') ---
    main(args.issue, args.project, args.delete_obsolete)