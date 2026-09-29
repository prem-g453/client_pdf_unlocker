import os
import re
import datetime
import bcrypt
import jwt
from typing import Optional, Tuple
from app.config import get_settings

settings = get_settings()

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


# --- Password Hashing with Bcrypt ---
def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


# --- JWT Session Tokens ---
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now_utc})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None


# --- Masking sensitive data ---
def mask_password(pwd: Optional[str]) -> str:
    """Mask password or PAN for safe display in UI or logs."""
    if not pwd:
        return "****"
    pwd = str(pwd).strip()
    if len(pwd) <= 4:
        return "****"
    if len(pwd) == 10 and PAN_REGEX.match(pwd.upper()):
        # e.g. ABCDE1234F -> ABCDE****F
        return f"{pwd[:5]}****{pwd[-1]}"
    # Generic masking: show first 2 and last 2
    return f"{pwd[:2]}{'*' * (len(pwd) - 4)}{pwd[-2:]}"


def validate_pan_format(pan: str) -> bool:
    """Check if PAN matches standard format ^[A-Z]{5}[0-9]{4}[A-Z]$."""
    if not pan or not isinstance(pan, str):
        return False
    return bool(PAN_REGEX.match(pan.strip().upper()))


# --- Magic Bytes & File Upload Validation ---
PDF_MAGIC_BYTES = b"%PDF-"
XLSX_MAGIC_BYTES = b"PK\x03\x04"
XLS_MAGIC_BYTES = b"\xd0\xcf\x11\xe0"


def validate_pdf_content(header_bytes: bytes) -> bool:
    """Validate if file starts with standard PDF magic bytes (%PDF-)."""
    return header_bytes.startswith(PDF_MAGIC_BYTES)


def validate_excel_content(header_bytes: bytes) -> bool:
    """Validate if file starts with valid Excel (xlsx ZIP or xls OLE) magic bytes."""
    return header_bytes.startswith(XLSX_MAGIC_BYTES) or header_bytes.startswith(XLS_MAGIC_BYTES)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename against path traversal, control chars, null bytes,
    and dangerous symbols.
    """
    if not filename:
        return "unnamed_file"
    
    # Strip path components
    basename = os.path.basename(filename)
    # Handle Windows backslashes if submitted from different OS
    basename = basename.split("\\")[-1].split("/")[-1]
    
    # Remove null bytes and control chars
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', basename)
    # Keep alphanumeric, dots, dashes, underscores, spaces
    cleaned = re.sub(r'[^a-zA-Z0-9._\- ]', '_', cleaned).strip()
    
    # Prevent hidden files or empty names
    cleaned = cleaned.lstrip(".")
    if not cleaned:
        cleaned = "sanitized_file"
        
    return cleaned
