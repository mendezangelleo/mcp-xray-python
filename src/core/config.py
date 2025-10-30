from dotenv import load_dotenv
import os

load_dotenv()

JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN")
JIRA_BASE = os.environ.get("JIRA_BASE")
DEFAULT_PROJECT_KEY = os.environ.get("DEFAULT_PROJECT_KEY")
RELATES_LINK_TYPE = os.environ.get("RELATES_LINK_TYPE")