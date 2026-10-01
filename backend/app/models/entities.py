import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Float,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="user", cascade="all, delete-orphan")
    connections = relationship("Connection", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    language = Column(String(10), default="en")  # en, hi, kn, ta, te, ml, bn
    auto_recover = Column(Boolean, default=False)
    
    # Approval rules
    ask_external_messages = Column(Boolean, default=True)
    ask_payments = Column(Boolean, default=True)
    ask_purchases = Column(Boolean, default=True)
    ask_deleting = Column(Boolean, default=True)
    ask_sensitive_info = Column(Boolean, default=True)
    threshold_people = Column(Integer, default=5)
    threshold_amount = Column(Float, default=50.0)

    user = relationship("User", back_populates="preferences")

class Goal(Base):
    __tablename__ = "goals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    language = Column(String(10), default="en")
    attachments = Column(JSON, default=list) # List[str]
    links = Column(JSON, default=list)       # List[str]
    deadline = Column(String(255), nullable=True)
    status = Column(String(50), default="created") # created, understood, planned, executing, completed, failed
    
    # Structured breakdown from LLM
    understanding = Column(JSON, nullable=True) # GoalUnderstanding dict
    clarifications = Column(JSON, nullable=True) # Questions and answers
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="goals")
    plans = relationship("Plan", back_populates="goal", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="goal", cascade="all, delete-orphan")

class Plan(Base):
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    goal_id = Column(String(36), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    goal = relationship("Goal", back_populates="plans")
    tasks = relationship("Task", back_populates="plan", cascade="all, delete-orphan", order_by="Task.order")
    executions = relationship("Execution", back_populates="plan")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    capability_id = Column(String(100), nullable=False)
    candidate_tool_ids = Column(JSON, default=list) # List[str]
    depends_on = Column(JSON, default=list)          # List[str] task IDs
    risk_level = Column(String(20), default="low")   # low, medium, high, critical
    requires_approval = Column(Boolean, default=False)
    action = Column(String(100), nullable=True)       # e.g. "web_search", "document_summarize"
    params = Column(JSON, nullable=True)              # LLM-generated structured params for this action
    description = Column(Text, nullable=True)         # human-readable task description
    status = Column(String(50), default="pending")   # pending, running, completed, failed, recovering, waiting_approval, rejected
    selected_tool_id = Column(String(100), nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)

    plan = relationship("Plan", back_populates="tasks")

class Execution(Base):
    __tablename__ = "executions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    goal_id = Column(String(36), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="running") # running, paused, waiting_approval, completed, failed, cancelled, stopped
    outcome = Column(String(50), nullable=True) # COMPLETED, PARTIALLY_COMPLETED, FAILED, BLOCKED, CANCELLED, STOPPED
    evidence_level = Column(String(50), nullable=True) # ACTION_REQUESTED, ACTION_EXECUTED, ACTION_VERIFIED, GOAL_ACHIEVED
    outcome_summary = Column(Text, nullable=True)
    progress = Column(Float, default=0.0)
    current_task_id = Column(String(36), nullable=True)
    current_action = Column(String(255), nullable=True)
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    goal = relationship("Goal", back_populates="executions")
    plan = relationship("Plan", back_populates="executions")
    user = relationship("User", back_populates="executions")
    events = relationship("ExecutionEvent", back_populates="execution", cascade="all, delete-orphan", order_by="ExecutionEvent.seq")
    approvals = relationship("Approval", back_populates="execution", cascade="all, delete-orphan")
    recoveries = relationship("Recovery", back_populates="execution", cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="execution", cascade="all, delete-orphan")

class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    execution_id = Column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), index=True, nullable=False)
    seq = Column(Integer, nullable=False, index=True)
    type = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=utc_now)
    task_id = Column(String(36), nullable=True)
    tool_id = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    params = Column(JSON, default=dict)
    payload = Column(JSON, default=dict)

    execution = relationship("Execution", back_populates="events")

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    execution_id = Column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(36), nullable=False)
    action = Column(String(255), nullable=False)
    target = Column(String(255), nullable=True)
    content = Column(JSON, nullable=False) # Exact payload preview
    payload_hash = Column(String(64), nullable=False) # SHA-256
    reason = Column(Text, nullable=False)
    risk = Column(String(20), nullable=False) # medium, high, critical
    consequences = Column(Text, nullable=True)
    status = Column(String(20), default="pending") # pending, approved, rejected, expired
    decided_by = Column(String(20), nullable=True) # ui, voice
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    execution = relationship("Execution", back_populates="approvals")

class Recovery(Base):
    __tablename__ = "recoveries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    execution_id = Column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(36), nullable=False)
    original_tool_id = Column(String(100), nullable=False)
    problem = Column(Text, nullable=False)
    alternative_tool_id = Column(String(100), nullable=True)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="pending") # pending, succeeded, failed, cancelled
    created_at = Column(DateTime, default=utc_now)

    execution = relationship("Execution", back_populates="recoveries")

class Verification(Base):
    __tablename__ = "verifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    execution_id = Column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(36), nullable=False)
    criterion = Column(Text, nullable=False)
    result = Column(String(20), nullable=False) # passed, failed
    evidence = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)

    execution = relationship("Execution", back_populates="verifications")

class Connection(Base):
    __tablename__ = "connections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    app_id = Column(String(100), nullable=False) # google_calendar, gmail, slack, github, browser, mcp, rest
    name = Column(String(100), nullable=False)
    status = Column(String(50), default="not_connected") # connected, not_connected, needs_reconnection, error, coming_soon
    auth_type = Column(String(50), default="oauth2") # oauth2, token, url, none
    encrypted_credentials = Column(Text, nullable=True)
    scopes = Column(JSON, default=list)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="connections")
    permissions = relationship("Permission", back_populates="connection", cascade="all, delete-orphan")

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    connection_id = Column(String(36), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)
    permission_key = Column(String(100), nullable=False) # e.g. read, search, create_drafts, send, delete
    label = Column(String(100), nullable=False)
    is_granted = Column(Boolean, default=True)
    is_sensitive = Column(Boolean, default=False)

    connection = relationship("Connection", back_populates="permissions")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False) # approval_needed, execution_completed, execution_failed, recovery_triggered
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="notifications")
