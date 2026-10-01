import re
import json
import asyncio
import time
from typing import Dict, Any, Optional, List
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.entities import Connection, Permission, Notification
from app.security.crypto import decrypt_secret, encrypt_secret
from app.core.config import settings

_REFRESH_LOCKS: Dict[str, asyncio.Lock] = {}

class ConnectionRevokedError(Exception):
    """Raised when an OAuth refresh token is revoked or permanently invalid."""
    pass

def redact_sensitive_data(data: Any) -> Any:
    """
    Central redaction utility that removes secrets, bearer tokens, OAuth refresh tokens,
    and passwords from logging, exceptions, and event payloads.
    """
    if isinstance(data, str):
        # Redact Google OAuth tokens (ya29.xxx)
        redacted = re.sub(r"ya29\.[A-Za-z0-9_\-\.]+", "[REDACTED_GOOGLE_TOKEN]", data)
        # Redact Bearer tokens
        redacted = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED_TOKEN]", redacted)
        # Redact JWT signatures
        redacted = re.sub(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[REDACTED_JWT]", redacted)
        return redacted
    elif isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ["token", "secret", "password", "credential", "refresh_token", "api_key", "authorization"]):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = redact_sensitive_data(v)
        return clean
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    return data

class ConnectionResolver:
    """
    Unified, credential-aware connection resolution and token refresh manager.
    Used by both standard task execution and failure recovery.
    """

    def _get_lock(self, connection_id: str) -> asyncio.Lock:
        if connection_id not in _REFRESH_LOCKS:
            _REFRESH_LOCKS[connection_id] = asyncio.Lock()
        return _REFRESH_LOCKS[connection_id]

    async def resolve(
        self,
        app_id: str,
        user_id: str,
        db: AsyncSession,
        required_permissions: Optional[List[str]] = None,
        allow_reconnection: bool = False
    ) -> Dict[str, Any]:
        """Convenience alias for resolve_connection."""
        return await self.resolve_connection(
            user_id=user_id,
            app_id=app_id,
            required_permissions=required_permissions or [],
            db=db,
            allow_reconnection=allow_reconnection
        )

    async def resolve_connection(
        self,
        user_id: str,
        app_id: str,
        required_permissions: List[str],
        db: AsyncSession,
        allow_reconnection: bool = False
    ) -> Dict[str, Any]:
        """
        Loads user connection, validates permissions, and ensures valid access credentials
        (auto-refreshing Google OAuth tokens if near expiration).
        """
        from sqlalchemy import or_
        stmt = (
            select(Connection)
            .options(selectinload(Connection.permissions))
            .where(Connection.user_id == user_id, or_(Connection.app_id == app_id, Connection.id == app_id))
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn:
            raise PermissionError(f"Connection '{app_id}' does not exist for this user.")

        if conn.status == "needs_reconnection" and not allow_reconnection:
            raise ConnectionRevokedError(f"Connection '{app_id}' requires re-authentication. Please reconnect in Connections.")

        from app.catalog.apps import get_app
        app_def = get_app(conn.app_id)
        needs_credentials = app_def.requires_credentials if app_def else True

        if conn.status != "connected":
            raise PermissionError(f"App '{conn.name}' is not connected. Please connect it in Connections.")

        if needs_credentials and not conn.encrypted_credentials:
            raise PermissionError(f"App '{conn.name}' is not configured with valid credentials.")

        # Validate required permissions
        if required_permissions is None:
            required_permissions = []
        elif isinstance(required_permissions, str):
            required_permissions = [required_permissions]
        granted_keys = {p.permission_key for p in conn.permissions if p.is_granted}
        for req_perm in required_permissions:
            if req_perm not in granted_keys:
                raise PermissionError(f"Permission '{req_perm}' is not granted for '{conn.name}'. Enable it in Connections.")

        if not needs_credentials:
            return {}

        # Decrypt stored credentials
        decrypted_str = decrypt_secret(conn.encrypted_credentials)
        if not decrypted_str:
            raise PermissionError(f"Could not decrypt stored credentials for '{conn.name}'.")

        try:
            cred_dict = json.loads(decrypted_str) if isinstance(decrypted_str, str) else decrypted_str
        except Exception:
            cred_dict = {"access_token": decrypted_str}

        # If MCP app, normalize config
        if conn.app_id == "mcp" or app_id.startswith("mcp"):
            from app.tools.adapters.mcp_client import parse_mcp_config
            cred_dict = parse_mcp_config(cred_dict)

        # If Google app, handle token refresh
        if app_id in ["google_calendar", "gmail"] and "refresh_token" in cred_dict:
            expires_at = cred_dict.get("expires_at", 0)
            now = time.time()
            # If expired or expiring in next 60 seconds, refresh
            if now >= (expires_at - 60):
                lock = self._get_lock(conn.id)
                async with lock:
                    # Re-check inside lock
                    if time.time() >= (cred_dict.get("expires_at", 0) - 60):
                        cred_dict = await self._refresh_google_token(conn, cred_dict, db)

        return cred_dict

    async def _refresh_google_token(
        self,
        conn: Connection,
        cred_dict: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Performs Google OAuth refresh token exchange."""
        refresh_token = cred_dict.get("refresh_token")
        if not refresh_token:
            return cred_dict

        client_id = settings.GOOGLE_CLIENT_ID
        client_secret = settings.GOOGLE_CLIENT_SECRET
        if not client_id or not client_secret:
            return cred_dict

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post("https://oauth2.googleapis.com/token", data=data)
            if res.status_code == 200:
                token_resp = res.json()
                new_access_token = token_resp.get("access_token")
                expires_in = token_resp.get("expires_in", 3600)
                
                cred_dict["access_token"] = new_access_token
                cred_dict["expires_at"] = time.time() + expires_in
                
                # Update encrypted credentials in DB
                conn.encrypted_credentials = encrypt_secret(json.dumps(cred_dict))
                conn.status = "connected"
                await db.commit()
                return cred_dict

            elif res.status_code in [400, 401]:
                # Token revoked or invalid
                conn.status = "needs_reconnection"
                
                notif = Notification(
                    user_id=conn.user_id,
                    type="reconnect_required",
                    title=f"{conn.name} Reconnection Required",
                    message="Google access authorization has expired or was revoked. Please reconnect.",
                    link="/connections"
                )
                db.add(notif)
                await db.commit()
                
                raise ConnectionRevokedError(f"Google token refresh failed (HTTP {res.status_code}). Connection marked as 'needs_reconnection'.")
            else:
                # Transient network failure
                return cred_dict

connection_resolver = ConnectionResolver()
