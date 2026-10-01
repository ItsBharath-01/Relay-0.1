# Relay 0.2 — Autonomous Work Operating System

Relay is a general-purpose autonomous work agent designed to execute real work across APIs, browser automation, local connectors, and Model Context Protocol (MCP) servers.

Unlike conversational chatbots, Relay is an execution-driven system:
```
GOAL 
→ UNDERSTANDING 
→ CLARIFICATION 
→ PLANNING 
→ TASK GRAPH 
→ CAPABILITY DISCOVERY 
→ TOOL DISCOVERY 
→ TOOL SELECTION 
→ RISK CHECK 
→ APPROVAL (if required) 
→ EXECUTION 
→ OBSERVATION 
→ VERIFICATION 
→ FAILURE DETECTION 
→ RECOVERY 
→ RE-PLANNING 
→ COMPLETION 
→ AUDIT HISTORY
```

---

## 🔒 Architectural Invariants & Security Principles

1. **LLM Never Executes Tools**: The LLM reasons and proposes structured parameters and plans only. The backend runtime strictly validates parameters, evaluates permissions, calculates risk scores, gates on human approvals, executes the real tools, and independently verifies state changes.
2. **LLM Never Sees Raw Credentials**: All secrets, OAuth tokens, and API keys are encrypted at rest using Fernet symmetric encryption and securely injected server-side right before tool invocation. Credentials are automatically redacted from all audit logs, traces, exceptions, and SSE streams.
3. **No Mocks in Production Integrations**: Real live HTTP and browser adapters are used for all connected applications. When user credentials are missing, Relay transparently reports missing configuration or marks connections as needing reconnection rather than fabricating synthetic success.
4. **SSRF & Path Traversal Protected**: REST adapters dynamically resolve DNS and block loopback, RFC-1918 private ranges, AWS/GCP metadata endpoints (`169.254.169.254`), and link-local addresses with a max redirect limit of 3. Filesystem tools are strictly sandboxed within the configured workspace directory (`RELAY_WORKSPACE_ROOT`).

---

## 🚀 Tech Stack

- **Backend**: Python 3.13, FastAPI, SQLAlchemy (async), aiosqlite, Pydantic v2, HTTPX, Cryptography (Fernet & bcrypt), Playwright.
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Zustand, Lucide React.
- **LLM Engine**: Local Ollama runtime (`http://localhost:11434`), default model: `qwen3:4b` with JSON schema enforcement and zero-thinking low-latency tuning.

---

## 🛠️ Integrated Tools & Capabilities

| Tool ID | Capability IDs | Connection Type | Auth Type |
|---|---|---|---|
| `web_search_engine` | `web_search` | Native | None |
| `web_reader` | `web_read`, `document_summarize` | Native | None |
| `playwright_browser` | `browser_navigate`, `web_read` | Local | None |
| `google_calendar` | `calendar_read`, `calendar_create`, `calendar_delete` | API | OAuth 2.0 (Google) |
| `gmail` | `email_read`, `email_draft`, `email_send` | API | OAuth 2.0 (Google) |
| `slack` | `message_send` | API | Bot Token (`xoxb-...`) |
| `github` | `issue_create`, `issue_read` | API | Personal Access Token (PAT) |
| `rest_connector` | `api_request` | REST / API | API Token / Header Key |
| `local_filesystem` | `file_read` | Local | Workspace Sandboxing |
| `mcp_tool` | `mcp_call` | MCP | Streamable HTTP / SSE endpoint |

---

## 💻 Getting Started

### 1. Prerequisites
- **Python**: 3.11+ (Python 3.13 tested)
- **Node.js**: 18+ (Node 20+ recommended)
- **Ollama**: Running locally at `http://localhost:11434` with model `qwen3:4b` pulled:
  ```bash
  ollama pull qwen3:4b
  ```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

Run backend:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation will be accessible at: `http://127.0.0.1:8000/docs`.

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Frontend Web UI will be available at: `http://127.0.0.1:5173`.

---

## 🧪 Testing & Verification

Relay maintains a strict 100% passing test bar across unit, integration, and security test suites.

### Run Backend Tests:
```bash
cd backend
.\venv\Scripts\python -m pytest tests/ -q
```
*Current test suite*: **134 passed, 0 failed**.

### Run Frontend Production Build:
```bash
cd frontend
npm run build
```
*Current build*: **1638 modules transformed, 0 TypeScript errors, exit code 0**.

---

## 📄 License
MIT License.
