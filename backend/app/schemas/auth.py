from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserPreferenceSchema(BaseModel):
    language: str = "en"
    auto_recover: bool = False
    ask_external_messages: bool = True
    ask_payments: bool = True
    ask_purchases: bool = True
    ask_deleting: bool = True
    ask_sensitive_info: bool = True
    threshold_people: int = 5
    threshold_amount: float = 50.0

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=100)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_active: bool
    created_at: datetime
    preferences: Optional[UserPreferenceSchema] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
