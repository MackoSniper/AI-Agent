import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

WORKING_DIR = os.path.join(PROJECT_ROOT, "agent_workspace")

os.makedirs(WORKING_DIR, exist_ok=True)

MAX_ITERS = 20
MAX_CHARS = 10000