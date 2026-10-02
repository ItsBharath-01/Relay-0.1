import json
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)
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
            "discovered_tools": c.discovered_tools or [],
            "scopes": c.scopes or [],
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
        "discovered_tools": conn.discovered_tools or [],
        "scopes": conn.scopes or [],
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
        from app.catalog.apps import get_app as _get_app
        app_def = _get_app(conn.app_id)
        if not app_def or not app_def.available:
            raise HTTPException(status_code=400, detail="This integration is coming soon and cannot be connected yet.")

    token_val = req.token or req.url or (req.credentials.get("access_token") if req.credentials else None)
    if not token_val:
        raise HTTPException(status_code=400, detail="Missing credential or token.")

    # Encrypt credentials at rest
    import json
    cred_json = json.dumps({"access_token": token_val, "url": req.url})
    conn.encrypted_credentials = encrypt_secret(cred_json)
    conn.status = "connected"

    # If this is an MCP connection, ensure permissions and trigger discovery
    if conn.app_id == "mcp":
        # Load permissions
        p_res = await db.execute(select(Permission).where(Permission.connection_id == conn.id))
        existing_perms = {p.permission_key: p for p in p_res.scalars().all()}
        for perm_key, perm_label, is_sensitive in [
            ("call_tools", "Call MCP Tools", True),
            ("list_tools", "List Available Tools", False),
            ("discover", "Discover MCP tools", False),
            ("execute", "Execute tools on external servers", True),
        ]:
            if perm_key in existing_perms:
                existing_perms[perm_key].is_granted = True
            else:
                p = Permission(
                    connection_id=conn.id,
                    permission_key=perm_key,
                    label=perm_label,
                    is_granted=True,
                    is_sensitive=is_sensitive,
                )
                db.add(p)

        try:
            from app.tools.adapters.mcp_client import parse_mcp_config
            norm_config = parse_mcp_config({"access_token": token_val, "url": req.url})
            discovered = await discover_and_register_mcp_tools(conn.id, conn.name, norm_config)
            conn.discovered_tools = discovered
            conn.scopes = [t["capability_id"] for t in discovered]
        except Exception as exc:
            logger.warning(f"Tool discovery on connect_app failed: {exc}")

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
    url: Optional[str] = None           # Base URL of the MCP server
    command: Optional[str] = None       # Command for stdio (e.g. "python", "node")
    args: Optional[List[str]] = None    # Arguments for stdio
    env: Optional[Dict[str, str]] = None
    transport: Optional[str] = None    # "streamable_http" | "stdio" | "sse"
    description: str = ""

@router.post("/mcp/register")
async def register_mcp_server(
    req: MCPServerRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.tools.adapters.mcp_client import mcp_client, parse_mcp_config, validate_mcp_config
    from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Server name is required.")

    # Build config payload
    config_dict = {
        "transport": req.transport,
        "server_url": req.url,
        "command": req.command,
        "args": req.args or [],
        "env": req.env or {},
    }
    try:
        norm_config = parse_mcp_config(config_dict)
        validate_mcp_config(norm_config)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # Health check server before saving
    adapter = _MCPAdapter()
    healthy, health_msg = await adapter.health_check(credentials=norm_config)
    if not healthy:
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to MCP server: {health_msg if isinstance(health_msg, str) else 'Unreachable'}"
        )

    # Use single static app_id for MCP in Relay 0.2 to match the tool registry
    app_id = "mcp"

    existing_res = await db.execute(
        select(Connection).where(
            Connection.user_id == current_user.id,
            Connection.app_id == app_id,
        )
    )
    existing = existing_res.scalar_one_or_none()
    
    cred_json = json.dumps(norm_config)
    enc_creds = encrypt_secret(cred_json)

    if existing:
        existing.name = name
        existing.encrypted_credentials = enc_creds
        existing.status = "connected"
        conn = existing
        # For existing connection, ensure permissions are granted if present
        if conn.permissions:
            for p in conn.permissions:
                if p.permission_key in ["call_tools", "list_tools", "execute", "discover"]:
                    p.is_granted = True
    else:
        conn = Connection(
            user_id=current_user.id,
            app_id=app_id,
            name=name,
            status="connected",
            auth_type="url" if norm_config["transport"] != "stdio" else "local",
            encrypted_credentials=enc_creds,
        )
        db.add(conn)
        await db.flush()

        for perm_key, perm_label, is_sensitive in [
            ("call_tools", "Call MCP Tools", True),
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

    # Discover and dynamically register tools
    try:
        discovered = await discover_and_register_mcp_tools(conn.id, name, norm_config)
        conn.discovered_tools = discovered
        conn.scopes = [t["capability_id"] for t in discovered]
    except Exception as exc:
        logger.warning(f"Tool discovery on registration failed: {exc}")
        discovered = []

    await db.commit()
    await db.refresh(conn)

    return {
        "id": conn.id,
        "app_id": conn.app_id,
        "name": conn.name,
        "url": norm_config.get("server_url"),
        "transport": norm_config.get("transport"),
        "status": conn.status,
        "health_message": health_msg if isinstance(health_msg, str) else (health_msg.get("message", "") if isinstance(health_msg, dict) else ""),
        "discovered_tools": discovered,
        "tool_count": len(discovered),
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
            "discovered_tools": s.discovered_tools or [],
            "tool_count": len(s.discovered_tools or []),
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
    adapter = _MCPAdapter()
    try:
        tools = await adapter.list_tools(server_url)
        conn.discovered_tools = tools
        await db.commit()
    except Exception as exc:
        if conn.discovered_tools:
            tools = conn.discovered_tools
        else:
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
        return {"status": "not_connected", "message": "No server configuration."}

    resolver = ConnectionResolver()
    credentials = await resolver.resolve(conn.app_id, current_user.id, db, allow_reconnection=True)
    from app.tools.adapters.mcp_client import mcp_client
    from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools

    healthy, health_info = await mcp_client.health_check(credentials)
    conn.status = "connected" if healthy else "error"
    from datetime import datetime, timezone
    conn.last_checked_at = datetime.now(timezone.utc)

    if healthy:
        try:
            tools = await discover_and_register_mcp_tools(conn.id, conn.name, credentials)
            conn.discovered_tools = tools
            conn.scopes = [t["capability_id"] for t in tools]
        except Exception as e:
            logger.warning(f"Failed to refresh tools: {e}")

    await db.commit()

    return {
        "connection_id": connection_id,
        "status": conn.status,
        "healthy": healthy,
        "message": health_info.get("message"),
        "transport": health_info.get("transport"),
        "tool_count": health_info.get("tool_count", 0),
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

    # Unregister dynamic tools for this connection from registry
    from app.tools.registry import unregister_tool, get_all_tools
    to_remove = [t.id for t in get_all_tools() if getattr(t, "connection_id", None) == conn.id]
    for tid in to_remove:
        unregister_tool(tid)

    await db.delete(conn)
    await db.commit()
    return {"status": "removed", "connection_id": connection_id}



# ══════════════════════════════════════════════════════════════════════════════
# Connection Health Check
# ══════════════════════════════════════════════════════════════════════════════
import asyncio
from datetime import datetime, timezone
from app.connections.resolver import ConnectionResolver
from app.tools.registry import get_tool, get_tools_for_capability


@router.get("/{connection_id}/health")
async def check_connection_health(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Runs a real health check via the adapter's health_check().
    Updates connection status in DB. Never exposes credentials in response.
    """
    stmt = select(Connection).where(
        Connection.id == connection_id,
        Connection.user_id == current_user.id,
    )
    res = await db.execute(stmt)
    conn = res.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    checked_at = datetime.now(timezone.utc).isoformat()

    # Special handling for MCP connections
    if conn.app_id == "mcp":
        credentials = None
        if conn.encrypted_credentials:
            try:
                resolver = ConnectionResolver()
                credentials = await resolver.resolve(conn.app_id, current_user.id, db, allow_reconnection=True)
            except Exception:
                credentials = None

        from app.tools.adapters.mcp_client import mcp_client
        from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools
        healthy, health_info = await mcp_client.health_check(credentials)
        if healthy:
            conn.status = "connected"
            try:
                tools = await discover_and_register_mcp_tools(conn.id, conn.name, credentials)
                conn.discovered_tools = tools
                conn.scopes = [t["capability_id"] for t in tools]
            except Exception as e:
                logger.warning(f"Tool refresh error during health check: {e}")
        else:
            conn.status = "needs_reconnection"

        await db.commit()
        return {
            "connection_id": connection_id,
            "status": "healthy" if healthy else "degraded",
            "message": health_info.get("message", "OK" if healthy else "Health check failed."),
            "server": health_info.get("server"),
            "transport": health_info.get("transport"),
            "tool_count": health_info.get("tool_count", 0),
            "checked_at": checked_at,
        }

    # Find the tool adapter for other connections
    tool = get_tool(conn.app_id)
    if not tool:
        caps = get_tools_for_capability(conn.app_id)
        tool = caps[0] if caps else None

    if not tool:
        return {
            "connection_id": connection_id,
            "status": "unavailable",
            "message": "No tool registered for this connection type.",
            "checked_at": checked_at,
        }

    # Resolve credentials without ever exposing them
    credentials = None
    if conn.encrypted_credentials:
        try:
            resolver = ConnectionResolver()
            credentials = await resolver.resolve(conn.app_id, current_user.id, db, allow_reconnection=True)
        except Exception:
            credentials = None

    try:
        healthy, message = await asyncio.wait_for(
            tool.health_check(credentials), timeout=10.0
        )
        conn.status = "connected" if healthy else "needs_reconnection"
        await db.commit()
        return {
            "connection_id": connection_id,
            "status": "healthy" if healthy else "degraded",
            "message": message or ("OK" if healthy else "Health check failed."),
            "checked_at": checked_at,
        }
    except asyncio.TimeoutError:
        conn.status = "needs_reconnection"
        await db.commit()
        return {
            "connection_id": connection_id,
            "status": "degraded",
            "message": "Health check timed out after 10 seconds.",
            "checked_at": checked_at,
        }
    except Exception:
        return {
            "connection_id": connection_id,
            "status": "unavailable",
            "message": "Health check raised an unexpected error.",
            "checked_at": checked_at,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Init Connection from Catalog (for non-OAuth apps)
# ══════════════════════════════════════════════════════════════════════════════
import uuid as _uuid
from app.catalog.apps import get_app as _get_catalog_app


@router.post("/catalog/{app_id}/init")
async def init_connection_from_catalog(
    app_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a bare Connection row for a catalog app if one does not yet exist.
    Local tools (browser, filesystem) are marked connected immediately.
    """
    app_def = _get_catalog_app(app_id)
    if not app_def:
        raise HTTPException(status_code=404, detail=f"App '{app_id}' not found in catalog.")
    if not app_def.available:
        raise HTTPException(status_code=400, detail=f"'{app_def.name}' is coming soon.")

    existing_res = await db.execute(
        select(Connection).where(
            Connection.user_id == current_user.id,
            Connection.app_id == app_id,
        )
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        return {"connection_id": existing.id, "status": existing.status, "already_existed": True}

    # Local tools need no credentials; mark connected immediately
    initial_status = "connected" if not app_def.requires_credentials else "not_connected"

    new_conn = Connection(
        id=str(_uuid.uuid4()),
        user_id=current_user.id,
        app_id=app_id,
        name=app_def.name,
        status=initial_status,
        auth_type=app_def.connection_type,
    )
    db.add(new_conn)
    await db.commit()
    return {"connection_id": new_conn.id, "status": initial_status, "already_existed": False}
