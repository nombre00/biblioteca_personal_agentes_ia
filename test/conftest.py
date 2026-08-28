import os
from pathlib import Path

from dotenv import load_dotenv

ENV_TEST_PATH = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(dotenv_path=ENV_TEST_PATH, override=False)