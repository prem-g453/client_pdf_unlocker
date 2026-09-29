from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    UserResponse, UserCreate, UserToggleRequest, AuditLogListResponse
)
from app.auth import require_admin
from app.security import hash_password
from app.services.audit_service import get_audit_logs, export_audit_logs_csv

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """List all registered system users."""
    users = db.query(User).order_by(User.id).all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse)
async def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Create a new user (Admin or Staff)."""
    clean_username = payload.username.strip()
    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{clean_username}' is already taken."
        )

    new_user = User(
        username=clean_username,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserResponse.model_validate(new_user)


@router.post("/users/{user_id}/toggle", response_model=UserResponse)
async def toggle_user_active_status(
    user_id: int,
    payload: UserToggleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Activate or deactivate a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own active status."
        )

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Retrieve audit logs with pagination and search."""
    return get_audit_logs(db, page=page, page_size=page_size, username=username)


@router.get("/audit-logs/export")
async def export_audit_logs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Export all audit logs to a CSV file (NO PASSWORDS)."""
    csv_data = export_audit_logs_csv(db)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=pdf_unlocker_audit_log.csv"
        }
    )
