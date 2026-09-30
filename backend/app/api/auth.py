from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.entities import User, UserPreference, Connection, Permission
from app.schemas.auth import UserCreate, UserLogin, UserResponse, Token, UserPreferenceSchema, PasswordChangeRequest
from app.security.crypto import get_password_hash, verify_password, create_access_token
from app.security.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

DEFAULT_APP_CONNECTIONS = [
    {
        "app_id": "google_calendar",
        "name": "Google Calendar",
        "auth_type": "oauth2",
        "status": "not_connected",
        "permissions": [
            {"key": "read", "label": "Read calendar events and availability", "is_sensitive": False},
            {"key": "create", "label": "Create and schedule new events", "is_sensitive": False},
            {"key": "delete", "label": "Delete or cancel existing events", "is_sensitive": True},
        ]
    },
    {
        "app_id": "gmail",
        "name": "Gmail",
        "auth_type": "oauth2",
        "status": "not_connected",
        "permissions": [
            {"key": "read", "label": "Read emails and threads", "is_sensitive": False},
            {"key": "draft", "label": "Create and update drafts", "is_sensitive": False},
            {"key": "send", "label": "Send emails to external contacts", "is_sensitive": True},
            {"key": "delete", "label": "Delete or trash emails", "is_sensitive": True},
        ]
    },
    {
        "app_id": "browser",
        "name": "Playwright Headless Browser",
        "auth_type": "none",
        "status": "connected", # Local browser automation is built-in
        "permissions": [
            {"key": "navigate", "label": "Navigate public web pages", "is_sensitive": False},
            {"key": "extract", "label": "Extract text and structured data", "is_sensitive": False},
            {"key": "interact", "label": "Click buttons and fill forms", "is_sensitive": True},
        ]
    },
    {
        "app_id": "slack",
        "name": "Slack",
        "auth_type": "oauth2",
        "status": "coming_soon",
        "permissions": [
            {"key": "read", "label": "Read channel messages", "is_sensitive": False},
            {"key": "send", "label": "Send messages to channels", "is_sensitive": True},
        ]
    },
    {
        "app_id": "github",
        "name": "GitHub",
        "auth_type": "oauth2",
        "status": "coming_soon",
        "permissions": [
            {"key": "read", "label": "Read issues and repos", "is_sensitive": False},
            {"key": "create_issue", "label": "Create new issues", "is_sensitive": False},
        ]
    },
    {
        "app_id": "mcp",
        "name": "Model Context Protocol (MCP)",
        "auth_type": "url",
        "status": "coming_soon",
        "permissions": [
            {"key": "discover", "label": "Discover MCP tools", "is_sensitive": False},
            {"key": "execute", "label": "Execute tools on external servers", "is_sensitive": True},
        ]
    },
    {
        "app_id": "rest_connector",
        "name": "REST API Connector",
        "auth_type": "token",
        "status": "coming_soon",
        "permissions": [
            {"key": "request", "label": "Execute configured API calls", "is_sensitive": True},
        ]
    }
]

@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Registers a new user and provisions default connections and preferences."""
    # Check if email exists
    stmt = select(User).where(User.email == user_in.email)
    existing = await db.execute(stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )

    # Create User
    new_user = User(
        email=user_in.email,
        name=user_in.name,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(new_user)
    await db.flush()

    # Create Preferences
    prefs = UserPreference(user_id=new_user.id)
    db.add(prefs)

    # Provision standard connections & granular permissions
    for app_meta in DEFAULT_APP_CONNECTIONS:
        conn = Connection(
            user_id=new_user.id,
            app_id=app_meta["app_id"],
            name=app_meta["name"],
            auth_type=app_meta["auth_type"],
            status=app_meta["status"],
        )
        db.add(conn)
        await db.flush()

        for p in app_meta["permissions"]:
            perm = Permission(
                connection_id=conn.id,
                permission_key=p["key"],
                label=p["label"],
                is_granted=True,
                is_sensitive=p["is_sensitive"],
            )
            db.add(perm)

    await db.commit()

    # Reload user with preferences
    stmt = select(User).options(selectinload(User.preferences)).where(User.id == new_user.id)
    res = await db.execute(stmt)
    loaded_user = res.scalar_one()

    access_token = create_access_token({"sub": loaded_user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": loaded_user
    }

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticates user and returns JWT token."""
    stmt = select(User).options(selectinload(User.preferences)).where(User.email == credentials.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is disabled"
        )

    access_token = create_access_token({"sub": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user profile and preferences."""
    return current_user

@router.put("/preferences", response_model=UserPreferenceSchema)
async def update_preferences(
    prefs_in: UserPreferenceSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Updates user approval preferences and UI language."""
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    res = await db.execute(stmt)
    pref = res.scalar_one_or_none()
    if not pref:
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)

    for field, val in prefs_in.model_dump().items():
        setattr(pref, field, val)

    await db.commit()
    await db.refresh(pref)
    return pref

@router.post("/change-password")
async def change_password(
    req: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Safely updates user password."""
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    current_user.hashed_password = get_password_hash(req.new_password)
    await db.commit()
    return {"status": "ok", "message": "Password changed successfully"}
