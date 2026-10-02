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

1. **LLM Never Executes Tools**: The LLM reasons and proposes structured parameters and plans only. The backend runtime strictly validates parameters, evaluates permissions, calculates risk scores, gates on human approvals, executes real tools, and independently verifies state changes.
2. **LLM Never Sees Raw Credentials**: All secrets, OAuth tokens, and API keys are encrypted at rest using AES-256 (Fernet) and securely injected server-side right before tool invocation. Credentials are automatically redacted from all audit logs, traces, exceptions, and SSE streams.
3. **No Mocks in Production Integrations**: Real live HTTP and browser adapters are used for all connected applications. When user credentials are missing, Relay transparently reports missing configuration or marks connections as needing reconnection rather than fabricating synthetic success.
4. **SSRF & Sandbox Protected**: Outbound requests dynamically resolve DNS and block loopback, RFC-1918 private ranges, AWS/GCP/Azure metadata endpoints (`169.254.169.254`), and link-local addresses with a max redirect limit of 3. Filesystem tools are strictly sandboxed within the configured workspace directory (`RELAY_WORKSPACE_ROOT`).

---

## 🚀 Production Architecture

Relay is architected for production deployment across modern cloud infrastructure:

- **Frontend**: Single-Page App (SPA) hosted on **Vercel** with client-side rewrite rules (`vercel.json`).
- **Backend**: Async Python FastAPI service hosted on **Render** (Native Python Web Service or Docker).
- **Database**: Managed **PostgreSQL** (Render Postgres, Supabase, Neon, AWS RDS) using `asyncpg` with connection pooling and `pool_pre_ping`.
- **LLM**: Hosted production LLM (Hosted Ollama on private GPU VM / endpoint, or hosted model API).
- **Integrations**: OAuth 2.0 (Google Workspace / Calendar / Gmail), API Tokens (GitHub PAT, Slack Bot Tokens).
- **MCP**: Hosted HTTPS MCP servers over SSE or Streamable HTTP transport.

---

## 📦 Production Deployment Guide

### Phase 1: Generate Production Cryptographic Keys

Run the included cryptographic secret generator to produce high-entropy keys for JWT signing and AES-256 database encryption:

```bash
python scripts/generate_secrets.py
```

Output:
- `SECRET_KEY`: 32-byte hex string for signing access tokens.
- `ENCRYPTION_KEY`: URL-safe base64 Fernet key for encrypting credentials at rest.

> [!IMPORTANT]
> Keep `SECRET_KEY` and `ENCRYPTION_KEY` confidential. In `ENVIRONMENT=production`, Relay validates both keys on startup and refuses to start if default or placeholder values are detected.

---

### Phase 2: Database Setup (Managed PostgreSQL)

1. Provision a PostgreSQL 15+ database on **Render**, **Supabase**, **Neon**, or **AWS RDS**.
2. Retrieve your connection string. Render / cloud providers format URLs as:
   ```
   postgresql://user:password@hostname:5432/relay_db
   ```
3. Relay automatically normalizes `postgresql://` or `postgres://` to async `postgresql+asyncpg://` at runtime.
4. On startup, the backend automatically runs `init_db()` to create all tables and apply idempotent migrations.

---

### Phase 3: Backend Deployment (Render)

1. Connect your GitHub repository to **Render** and create a **Web Service**.
2. Configure the service settings:
   - **Environment**: `Python` (or `Docker`)
   - **Root Directory**: `backend` (or repo root)
   - **Build Command**:
     ```bash
     pip install -r requirements.txt && playwright install --with-deps chromium
     ```
   - **Start Command**:
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Health Check Path**: `/api/v1/health`
3. Configure the **Environment Variables** on Render:

| Variable | Required | Description / Example |
|---|---|---|
| `ENVIRONMENT` | **Yes** | `production` |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://user:pass@host:5432/relay_db` |
| `SECRET_KEY` | **Yes** | 32-byte hex key from `generate_secrets.py` |
| `ENCRYPTION_KEY` | **Yes** | Fernet base64 key from `generate_secrets.py` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | **Yes** | `60` (or desired session duration) |
| `FRONTEND_URL` | **Yes** | `https://relay-app.vercel.app` |
| `BACKEND_CORS_ORIGINS` | **Yes** | `https://relay-app.vercel.app` |
| `LLM_PROVIDER` | **Yes** | `ollama` (or `gemini` / `openai` / `anthropic`) |
| `OLLAMA_BASE_URL` | **Yes** | `https://ollama.yourdomain.com` |
| `OLLAMA_MODEL` | **Yes** | `qwen3:4b` |
| `OLLAMA_NUM_CTX` | Optional | `8192` |
| `OLLAMA_TIMEOUT` | Optional | `120` |
| `GOOGLE_CLIENT_ID` | Optional | Google OAuth Client ID (for Calendar & Gmail) |
| `GOOGLE_CLIENT_SECRET` | Optional | Google OAuth Client Secret |
| `GOOGLE_REDIRECT_URI` | Optional | `https://relay-backend.onrender.com/api/v1/connections/oauth/google/callback` |
| `SLACK_CLIENT_ID` | Optional | Slack App Client ID |
| `SLACK_CLIENT_SECRET` | Optional | Slack App Client Secret |
| `GITHUB_CLIENT_ID` | Optional | GitHub App Client ID |
| `GITHUB_CLIENT_SECRET` | Optional | GitHub App Client Secret |
| `ALLOW_PRIVATE_NETWORKS` | **Yes** | `false` (enforces strict SSRF protection) |
| `RELAY_DEV_ALLOW_LOCAL_MCP` | **Yes** | `false` (disallows localhost MCP in prod) |

---

### Phase 4: Frontend Deployment (Vercel)

1. Import the repository in **Vercel**.
2. Configure project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
   - **Install Command**: `npm install`
3. Add Environment Variable:
   - `VITE_API_URL`: URL of your Render backend (e.g. `https://relay-backend.onrender.com`)
4. Deploy! Vercel will automatically read `frontend/vercel.json` to handle single-page client routing.

---

### Phase 5: Google OAuth Setup (Optional for Calendar & Gmail)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Create an **OAuth 2.0 Client ID** (Web application).
3. Add **Authorized JavaScript origins**:
   - `https://relay-app.vercel.app`
4. Add **Authorized redirect URIs**:
   - `https://relay-backend.onrender.com/api/v1/connections/oauth/google/callback`
5. Enable the **Google Calendar API** and **Gmail API** in your Google Cloud project.
6. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in Render environment variables.

---

### Phase 6: Hosted HTTPS MCP Setup

1. In production, connect MCP servers using secure HTTPS URLs (e.g. `https://mcp-server.example.com/sse` or `https://mcp-server.example.com/mcp`).
2. Navigate to **Connections** in the Relay UI, choose **MCP Server**, and enter your hosted endpoint.
3. Relay's unified SSRF filter will resolve the public DNS, pin the IP, verify HTTPS, and dynamically discover and register tool capabilities.

---

## 🧪 Verification & Quality Bar

### 1. Backend Automated Tests (231+ tests passing)
```bash
cd backend
python -m pytest
```

### 2. Frontend TypeScript Check & Production Build
```bash
cd frontend
npm run lint    # Type check (tsc --noEmit)
npm run build   # Production Vite bundle
```

### 3. Repository Secrets Scanner
```bash
python scripts/scan_secrets.py
```

---

## 📄 License
MIT License.
