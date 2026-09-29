from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user_optional(
    request: Request,
    token_from_header: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Extract and authenticate user from Authorization Header, Cookie, or Query Param."""
    token = token_from_header or access_token
    
    # Check query parameter if needed (e.g. for SSE or file download triggers in browser)
    if not token and "token" in request.query_params:
        token = request.query_params["token"]
        
    if not token:
        return None
        
    payload = decode_access_token(token)
    if not payload:
        return None
        
    username: str = payload.get("sub")
    if not username:
        return None
        
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        return None
        
    return user


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Dependency requiring a valid authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency requiring an Admin user."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required.",
        )
    return current_user


async def require_staff_or_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency requiring Staff or Admin role."""
    if current_user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to authorized personnel.",
        )
    return current_user
