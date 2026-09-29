import os
import io
import shutil
import tempfile
import pytest
import openpyxl
import pikepdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.database as app_db
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import User
from app.security import hash_password

TEST_DB_URL = "sqlite:///./test_temp.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Point global SessionLocal to TestingSessionLocal for tests
app_db.SessionLocal = TestingSessionLocal
app_db.engine = test_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        # Create test admin
        admin = User(
            username="testadmin",
            hashed_password=hash_password("AdminPass123!"),
            role="admin",
            is_active=True
        )
        # Create test staff
        staff = User(
            username="teststaff",
            hashed_password=hash_password("StaffPass123!"),
            role="staff",
            is_active=True
        )
        db.add_all([admin, staff])
        db.commit()

    yield

    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test_temp.db"):
        try:
            os.remove("./test_temp.db")
        except Exception:
            pass


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def admin_token(client):
    res = client.post("/api/auth/login", json={"username": "testadmin", "password": "AdminPass123!"})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture
def staff_token(client):
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "StaffPass123!"})
    assert res.status_code == 200
    return res.json()["access_token"]


def create_sample_excel_bytes(rows, header=None) -> bytes:
    """Helper to create Excel bytes with openpyxl."""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    if header:
        ws.append(header)
        
    for r in rows:
        ws.append(r)
        
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def create_encrypted_pdf_bytes(password: str, content_text: str = "Test Portfolio Content") -> bytes:
    """Helper to create an encrypted PDF with a user password using pikepdf."""
    pdf = pikepdf.new()
    pdf.add_blank_page()
    
    buf = io.BytesIO()
    pdf.save(
        buf,
        encryption=pikepdf.Encryption(
            user=password,
            owner=f"owner_{password}",
            R=6
        )
    )
    return buf.getvalue()


def create_owner_only_encrypted_pdf_bytes(owner_password: str = "secretowner") -> bytes:
    """Helper to create a PDF with ONLY an owner password (no user password required to open)."""
    pdf = pikepdf.new()
    pdf.add_blank_page()
    
    buf = io.BytesIO()
    pdf.save(
        buf,
        encryption=pikepdf.Encryption(
            user="",  # empty user password
            owner=owner_password,
            allow=pikepdf.Permissions(print_lowres=True)
        )
    )
    return buf.getvalue()


def create_unencrypted_pdf_bytes() -> bytes:
    """Helper to create a standard unencrypted PDF."""
    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()
