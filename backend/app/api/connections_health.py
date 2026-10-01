

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

    # Find the tool adapter for this connection's app_id
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
            credentials = await resolver.resolve(conn.app_id, current_user.id, db)
        except Exception:
            credentials = None

    try:
        healthy, message = await asyncio.wait_for(
            tool.health_check(credentials), timeout=5.0
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
            "message": "Health check timed out after 5 seconds.",
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
