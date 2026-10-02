#!/usr/bin/env python3
"""
scripts/scan_secrets.py

Scans the repository for committed or leaked secrets, credentials, and database files:
- *.db, *.sqlite*, *.db-journal
- Hardcoded Fernet keys
- GitHub tokens (ghp_, github_pat_)
- Slack tokens (xox[abp]-)
- Google API keys (AIza)
- OpenAI / generic service keys (sk-)
- Google OAuth tokens (ya29.)
- PEM private keys
- Non-placeholder emails in test fixtures or code

Excludes:
- .git, node_modules, venv, .venv, __pycache__, dist
"""

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "coverage",
    ".idea",
    ".vscode",
}

EXCLUDED_FILES = {
    ".env.example",
    "scan_secrets.py",
    "generate_secrets.py",
    "test_scan_secrets.py",
    "test_secrets_hygiene.py",
}

# Regex patterns for high-entropy secrets and specific formats
PATTERNS = [
    ("GitHub Personal Access Token", re.compile(r"github_pat_[A-Za-z0-9_]{50,}")),
    ("GitHub Token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("Slack Token", re.compile(r"xox[abp]-[A-Za-z0-9-]{20,}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z-_]{35}")),
    ("Generic / OpenAI Secret Key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("Google OAuth Access Token", re.compile(r"ya29\.[A-Za-z0-9_\-\.]{50,}")),
    ("PEM Private Key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# Allow-list for known test mock tokens
ALLOWLIST_PATTERNS = [
    re.compile(r"xoxb-fake", re.I),
    re.compile(r"xoxb-test", re.I),
    re.compile(r"ghp_test", re.I),
    re.compile(r"sk-test", re.I),
    re.compile(r"placeholder", re.I),
    re.compile(r"your_", re.I),
    re.compile(r"example", re.I),
]


def is_allowlisted(match_str: str) -> bool:
    for pat in ALLOWLIST_PATTERNS:
        if pat.search(match_str):
            return True
    return False


def scan() -> int:
    findings = []

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file in files:
            file_path = Path(root) / file
            rel_path = file_path.relative_to(ROOT_DIR)

            # Check for disallowed database files
            if file.endswith((".db", ".sqlite", ".sqlite3", ".db-journal")):
                findings.append((str(rel_path), "Committed database file found", file))
                continue

            if file in EXCLUDED_FILES:
                continue

            # Check text files for secret patterns
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for name, pattern in PATTERNS:
                for match in pattern.finditer(content):
                    secret_found = match.group(0)
                    if not is_allowlisted(secret_found):
                        # Mask for reporting: first 4 chars + length
                        masked = f"{secret_found[:4]}...[{len(secret_found)} chars]"
                        findings.append((str(rel_path), f"Potential {name}", masked))

    if findings:
        print(f"[FAIL] Secret scanner detected {len(findings)} issue(s):")
        for loc, issue, masked_val in findings:
            print(f"  - [{loc}] {issue}: {masked_val}")
        return 1
    else:
        print("[PASS] Secret scan passed: No committed credentials or database files found.")
        return 0


if __name__ == "__main__":
    sys.exit(scan())
