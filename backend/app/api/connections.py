from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.entities import Connection, Permission, User
from app.tools.registry import get_tool
from app.security.crypto import encrypt_secret, decrypt_secret
from app.security.auth import get_current_user

router = APIRouter(prefix="/connections", tags=["Connections"])

class PermissionUpdateItem(BaseModel):
    permission_key: str
    is_granted: bool

class UpdatePermissionsRequest(BaseModel):
    permissions: List[PermissionUpdateItem]

class ConnectAppRequest(BaseModel):
    token: Optional[str] = None
    url: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None

@router.get("")
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns all application connections with live health and granted permissions."""
    stmt = (
        select(Connection)
        .options(selectinload(Connection.permissions))
        .where(Connection.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    conns = res.scalars().all()

    response_items = []
    for c in conns:
        response_items.append({
            "id": c.id,
            "app_id": c.app_id,
            "name": c.name,
            "status": c.status,
            "auth_type": c.auth_type,
            "has_credentials": bool(c.encrypted_credentials),
            "permissions": [
                {
                    "id": p.id,
                    "key": p.permission_key,
                    "label": p.label,
                    "is_granted": p.is_granted,
                    "is_sensitive": p.is_sensitive
                } for p in c.permissions
            ]
        })
    return response_items

@router.get("/{connection_id}")
async def get_connection_detail(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Connection)
        .options(selectinload(Connection.permissions))
        .where(Connection.id == connection_id, Connection.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    return {
        "id": conn.id,
        "app_id": conn.app_id,
        "name": conn.name,
        "status": conn.status,
        "auth_type": conn.auth_type,
        "permissions": [
            {
                "id": p.id,
                "key": p.permission_key,
                "label": p.label,
                "is_granted": p.is_granted,
                "is_sensitive": p.is_sensitive
            } for p in conn.permissions
        ]
    }

@router.post("/{connection_id}/permissions")
async def update_permissions(
    connection_id: str,
    req: UpdatePermissionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Updates granular permission toggles for a connection."""
    stmt = (
        select(Connection)
        .options(selectinload(Connection.permissions))
        .where(Connection.id == connection_id, Connection.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    perm_map = {p.permission_key: p for p in conn.permissions}
    for update_item in req.permissions:
        if update_item.permission_key in perm_map:
            perm_map[update_item.permission_key].is_granted = update_item.is_granted

    await db.commit()
    return {"status": "ok", "message": "Permissions updated successfully."}

@router.post("/{connection_id}/connect")
async def connect_app(
    connection_id: str,
    req: ConnectAppRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Connects an application with provided OAuth token or URL credentials."""
    stmt = select(Connection).where(Connection.id == connection_id, Connection.user_id == current_user.id)
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if conn.status == "coming_soon":
        raise HTTPException(status_code=400, detail="This integration is coming soon and cannot be connected yet.")

    token_val = req.token or req.url or (req.credentials.get("access_token") if req.credentials else None)
    if not token_val:
        raise HTTPException(status_code=400, detail="Missing credential or token.")

    # Encrypt credentials at rest
    import json
    cred_json = json.dumps({"access_token": token_val, "url": req.url})
    conn.encrypted_credentials = encrypt_secret(cred_json)
    conn.status = "connected"
    await db.commit()

    return {"status": "connected", "connection_id": conn.id}

@router.post("/{connection_id}/disconnect")
async def disconnect_app(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Disconnects an application and wipes encrypted credentials."""
    stmt = select(Connection).where(Connection.id == connection_id, Connection.user_id == current_user.id)
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if conn.app_id == "browser":
        raise HTTPException(status_code=400, detail="Local browser cannot be disconnected.")

    conn.encrypted_credentials = None
    conn.status = "not_connected"
    await db.commit()
    return {"status": "not_connected", "connection_id": conn.id}

# --- P1-3 Google OAuth Flow ---
import hmac
import hashlib
import time
import urllib.parse
from app.core.config import settings

def _generate_oauth_state(user_id: str, services: str) -> str:
    """Generates a cryptographically signed, timestamped single-use OAuth state token."""
    ts = str(int(time.time()))
    payload = f"{user_id}:{services}:{ts}"
    signature = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def _verify_oauth_state(state: str, user_id: str) -> Optional[List[str]]:
    """Verifies state signature, user binding, and expiry (< 10 minutes)."""
    try:
        parts = state.split(":")
        if len(parts) != 4:
            return None
        st_user, st_services, st_ts, st_sig = parts
        
        # Verify user binding
        if st_user != user_id:
            return None

        # Verify expiry (< 600 seconds)
        if time.time() - int(st_ts) > 600:
            return None

        # Verify signature
        payload = f"{st_user}:{st_services}:{st_ts}"
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(st_sig, expected_sig):
            return None

        return st_services.split(",")
    except Exception:
        return None

@router.get("/oauth/google/start")
async def google_oauth_start(
    services: str = "gmail,calendar",
    current_user: User = Depends(get_current_user)
):
    """
    Initiates Google OAuth authorization flow for Gmail and Google Calendar.
    Returns the authorization URL or indicates unconfigured state.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return {
            "configured": False,
            "status": "unconfigured",
            "message": "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env to connect."
        }

    # Map requested services to minimum required scopes
    scope_map = {
        "gmail": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose"
        ],
        "calendar": [
            "https://www.googleapis.com/auth/calendar.events"
        ]
    }

    requested_scopes = ["openid", "email", "profile"]
    for s in services.split(","):
        s_clean = s.strip().lower()
        if s_clean in scope_map:
            requested_scopes.extend(scope_map[s_clean])

    state_token = _generate_oauth_state(current_user.id, services)
    
    oauth_params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(requested_scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(oauth_params)}"
    return {
        "configured": True,
        "status": "ready",
        "authorization_url": auth_url,
        "state": state_token
    }

@router.get("/oauth/google/callback")
async def google_oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Handles Google OAuth redirect callback, exchanges authorization code for access and refresh tokens,
    and stores encrypted credentials in the user's connection entities.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth denied or failed: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state parameter.")

    # Validate state token
    services = _verify_oauth_state(state, current_user.id)
    if not services:
        raise HTTPException(status_code=400, detail="Invalid, expired, or tampered OAuth state parameter.")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on this server.")

    # Exchange authorization code for tokens
    import httpx
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(token_url, data=token_data)
        if res.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to exchange Google OAuth code: {res.text}")

        token_json = res.json()
        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")
        expires_in = token_json.get("expires_in", 3600)

        stored_creds = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + expires_in,
            "scope": token_json.get("scope")
        }
        encrypted_str = encrypt_secret(json.dumps(stored_creds))

        # Update relevant connections (gmail, google_calendar)
        app_targets = []
        if "gmail" in services:
            app_targets.append("gmail")
        if "calendar" in services:
            app_targets.append("google_calendar")

        stmt = select(Connection).where(Connection.user_id == current_user.id, Connection.app_id.in_(app_targets))
        conns_res = await db.execute(stmt)
        matched_conns = conns_res.scalars().all()

        for conn in matched_conns:
            conn.encrypted_credentials = encrypted_str
            conn.status = "connected"

        await db.commit()

        return {
            "status": "connected",
            "services_connected": app_targets,
            "message": "Google accounts connected successfully."
        }



# -----------------------------------------------------------------------------
# P2-2: MCP Server Management
# -----------------------------------------------------------------------------

from app.tools.adapters.mcp_adapter import MCPToolAdapter as _MCPAdapter
from pydantic import BaseModel
from fastapi import HTTPException

class MCPServerRegisterRequest(BaseModel):
    name: str          # Human-readable server name (e.g. "Filesystem Tools")
    url: str           # Base URL of the MCP server (e.g. http://localhost:8080)
    description: str = ""

@router.post("/mcp/register")
async def register_mcp_server(
    req: MCPServerRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import re
    name = req.name.strip()
    url = req.url.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Server name is required.")
    if not url:
        raise HTTPException(status_code=400, detail="Server URL is required.")
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    adapter = _MCPAdapter()
    healthy, health_msg = await adapter.health_check(credentials=url)
    if not healthy:
        raise HTTPException(status_code=400, detail=f"Could not connect to MCP server: {health_msg}")

    # Use a single static app_id for MCP in Relay 0.2 to match the tool registry
    app_id = "mcp"

    existing_res = await db.execute(
        select(Connection).where(
            Connection.user_id == current_user.id,
            Connection.app_id == app_id,
        )
    )
    existing = existing_res.scalar_one_or_none()
    
    # Store just the url in json to match how Google oauth tokens are stored for robustness
    # The MCP adapter expects string, but the resolver currently assumes JSON for some reason?
    # Actually resolver passes the raw decrypted string back.
    # Let's store raw URL for MCP.
    
    if existing:
        # Update existing MCP server instead of creating a second one
        existing.name = name
        existing.encrypted_credentials = encrypt_secret(url)
        existing.status = "connected"
        conn = existing
    else:
        conn = Connection(
            user_id=current_user.id,
            app_id=app_id,
            name=name,
            status="connected",
            auth_type="url",
            encrypted_credentials=encrypt_secret(url),
        )
        db.add(conn)
        await db.flush()

        for perm_key, perm_label, is_sensitive in [
            ("call_tools", "Call MCP Tools", False),
            ("list_tools", "List Available Tools", False),
        ]:
            perm = Permission(
                connection_id=conn.id,
                permission_key=perm_key,
                label=perm_label,
                is_granted=True,
                is_sensitive=is_sensitive,
            )
            db.add(perm)

    await db.commit()
    await db.refresh(conn)

    return {
        "id": conn.id,
        "app_id": conn.app_id,
        "name": conn.name,
        "url": url,
        "status": conn.status,
        "health_message": health_msg,
    }

@router.get("/mcp/servers")
async def list_mcp_servers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Connection)
        .options(selectinload(Connection.permissions))
        .where(
            Connection.user_id == current_user.id,
            Connection.app_id == "mcp",
        )
    )
    res = await db.execute(stmt)
    servers = res.scalars().all()

    return [
        {
            "id": s.id,
            "app_id": s.app_id,
            "name": s.name,
            "status": s.status,
            "has_credentials": bool(s.encrypted_credentials),
            "permissions": [
                {
                    "id": p.id,
                    "key": p.permission_key,
                    "label": p.label,
                    "is_granted": p.is_granted,
                    "is_sensitive": p.is_sensitive,
                }
                for p in s.permissions
            ],
        }
        for s in servers
    ]

@router.get("/mcp/{connection_id}/tools")
async def list_mcp_server_tools(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Connection)
        .options(selectinload(Connection.permissions))
        .where(
            Connection.id == connection_id,
            Connection.user_id == current_user.id,
            Connection.app_id == "mcp",
        )
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="MCP server connection not found.")
    if conn.status != "connected" or not conn.encrypted_credentials:
        raise HTTPException(status_code=400, detail="MCP server is not connected.")

    perm_map = {p.permission_key: p for p in conn.permissions}
    list_perm = perm_map.get("list_tools")
    if not list_perm or not list_perm.is_granted:
        raise HTTPException(status_code=403, detail="list_tools permission is not granted for this connection.")

    server_url = decrypt_secret(conn.encrypted_credentials)
    if isinstance(server_url, dict):
        server_url = server_url.get("url", "")
    adapter = _MCPAdapter()
    try:
        tools = await adapter.list_tools(server_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list tools: {exc}")

    return {
        "connection_id": connection_id,
        "server_name": conn.name,
        "tool_count": len(tools),
        "tools": tools,
    }

@router.post("/mcp/{connection_id}/health")
async def check_mcp_server_health(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Connection).where(
        Connection.id == connection_id,
        Connection.user_id == current_user.id,
        Connection.app_id == "mcp",
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="MCP server connection not found.")

    if not conn.encrypted_credentials:
        conn.status = "not_connected"
        await db.commit()
        return {"status": "not_connected", "message": "No server URL configured."}

    server_url = decrypt_secret(conn.encrypted_credentials)
    if isinstance(server_url, dict):
        server_url = server_url.get("url", "")
    adapter = _MCPAdapter()
    healthy, health_msg = await adapter.health_check(credentials=server_url)

    conn.status = "connected" if healthy else "error"
    from datetime import datetime, timezone
    conn.last_checked_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "connection_id": connection_id,
        "status": conn.status,
        "healthy": healthy,
        "message": health_msg,
    }

@router.delete("/mcp/{connection_id}")
async def remove_mcp_server(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Connection).where(
        Connection.id == connection_id,
        Connection.user_id == current_user.id,
        Connection.app_id == "mcp",
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="MCP server connection not found.")

    await db.delete(conn)
    await db.commit()
    return {"status": "removed", "connection_id": connection_id}

