import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

WORKING_DIR = os.path.join(PROJECT_ROOT, "agent_workspace")

os.makedirs(WORKING_DIR, exist_ok=True)

MAX_ITERS = 20

# Tools that need the user's explicit approval before they run (used by both the CLI and the app).
SENSITIVE_FUNCTIONS = ["write_file", "run_python_file", "install_package"]
MAX_CHARS = 10000