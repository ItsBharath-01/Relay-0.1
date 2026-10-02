import os
import pytest

# Ensure tests run with ENVIRONMENT=test unless explicitly set
os.environ.setdefault("ENVIRONMENT", "test")
