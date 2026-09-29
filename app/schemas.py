import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserBase(BaseModel):
    username: str
    role: str = "staff"
    is_active: bool = True


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: str = Field("staff", pattern="^(admin|staff)$")


class UserResponse(UserBase):
    id: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class UserToggleRequest(BaseModel):
    is_active: bool


# --- Excel Validation Schemas ---
class ExcelRowWarning(BaseModel):
    row_number: int
    client_name: Optional[str] = ""
    masked_password: Optional[str] = ""
    reason: str
    action: str  # "Skipped" or "Kept as non-PAN"


class ExcelValidationResult(BaseModel):
    total_rows_read: int
    valid_count: int
    warning_count: int
    duplicate_count: int
    warnings: List[ExcelRowWarning]
    preview_entries: List[Dict[str, Any]]  # masked preview for first few records


# --- Job & Unlock Schemas ---
class FileProcessResult(BaseModel):
    file_id: str
    original_filename: str
    output_filename: Optional[str] = None
    status: str  # "UNLOCKED", "ALREADY_UNLOCKED", "NO_MATCH", "ERROR"
    matched_client: Optional[str] = None
    error_message: Optional[str] = None
    download_url: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "pending", "processing", "completed", "failed"
    total_files: int
    processed_files: int
    unlocked_count: int
    already_unlocked_count: int
    no_match_count: int
    error_count: int
    percent_complete: float
    is_completed: bool
    results: List[FileProcessResult] = []
    created_at: float
    duration_seconds: Optional[float] = None
    summary_message: Optional[str] = None


# --- Audit Schemas ---
class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime.datetime
    username: str
    job_id: str
    total_files: int
    unlocked_count: int
    already_unlocked_count: int
    no_match_count: int
    error_count: int
    duration_seconds: float
    file_details: Optional[List[Dict[str, Any]]] = None
    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogResponse]
