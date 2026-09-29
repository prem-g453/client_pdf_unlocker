import os
import shutil
import tempfile
import pytest
import pikepdf

from tests.conftest import (
    create_encrypted_pdf_bytes,
    create_owner_only_encrypted_pdf_bytes,
    create_unencrypted_pdf_bytes
)
from app.services.pdf_service import (
    attempt_unlock_pdf,
    PDFUnlockStatus,
    get_prioritized_candidates,
    generate_output_filename,
    extract_last_4_pan_digits
)


@pytest.fixture
def temp_io_dirs():
    base_dir = tempfile.mkdtemp()
    input_dir = os.path.join(base_dir, "inputs")
    output_dir = os.path.join(base_dir, "outputs")
    os.makedirs(input_dir)
    os.makedirs(output_dir)
    
    yield input_dir, output_dir
    
    shutil.rmtree(base_dir, ignore_errors=True)


def test_unlock_encrypted_pdf_exact_pan(temp_io_dirs):
    """Test unlocking PDF with exact PAN password."""
    input_dir, output_dir = temp_io_dirs
    pan = "ABCDE1234F"
    
    pdf_bytes = create_encrypted_pdf_bytes(pan)
    pdf_path = os.path.join(input_dir, "portfolio_report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    candidates = [
        {"name": "Other Client", "password": "ZYXWV9876A"},
        {"name": "Target Client", "password": pan}
    ]
    session_cache = {}

    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, session_cache)
    
    assert res["status"] == PDFUnlockStatus.UNLOCKED
    assert res["matched_client"] == "Target Client"
    assert res["output_filename"] == "Target_Client_1234_unlocked.pdf"
    assert os.path.exists(res["output_path"])
    
    # Verify the output PDF is truly unencrypted and readable with pikepdf without password
    with pikepdf.open(res["output_path"]) as opened_pdf:
        assert not getattr(opened_pdf, "is_encrypted", False)

    # Verify session cache updated
    assert session_cache["Target Client"] == pan


def test_unlock_case_insensitive_pan_variants(temp_io_dirs):
    """Test unlocking PDF where password in PDF is lowercase or uppercase."""
    input_dir, output_dir = temp_io_dirs
    
    # PDF was encrypted with lowercase pan
    pdf_bytes = create_encrypted_pdf_bytes("bkpk7654m")
    pdf_path = os.path.join(input_dir, "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Excel candidate has uppercase PAN
    candidates = [{"name": "Priya Sharma", "password": "BKPK7654M"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})
    
    assert res["status"] == PDFUnlockStatus.UNLOCKED
    assert res["matched_client"] == "Priya Sharma"


def test_prioritized_name_matching(temp_io_dirs):
    """Test prioritizing candidate whose name appears in PDF filename."""
    candidates = [
        {"name": "John Doe", "password": "JOHND1234F"},
        {"name": "Alice Smith", "password": "ALICE1234A"},
        {"name": "Robert Brown", "password": "ROBRT1234B"}
    ]
    session_cache = {}

    # Filename contains Alice Smith
    prioritized = get_prioritized_candidates("Alice_Smith_Q4_Portfolio.pdf", candidates, session_cache)
    
    assert len(prioritized) == 3
    # Alice should be first in prioritized list
    assert prioritized[0][0] == "Alice Smith"
    assert prioritized[0][1] == "ALICE1234A"


def test_already_unlocked_pdf_passthrough(temp_io_dirs):
    """Test that an unencrypted PDF is marked 'Already unlocked' and copied through."""
    input_dir, output_dir = temp_io_dirs
    pdf_bytes = create_unencrypted_pdf_bytes()
    pdf_path = os.path.join(input_dir, "annual_report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    candidates = [{"name": "Any User", "password": "ABCDE1234F"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})

    assert res["status"] == PDFUnlockStatus.ALREADY_UNLOCKED
    assert res["output_filename"] == "annual_report_unlocked.pdf"
    assert os.path.exists(res["output_path"])


def test_owner_password_only_pdf(temp_io_dirs):
    """Test PDF with owner password only is saved without restrictions."""
    input_dir, output_dir = temp_io_dirs
    pdf_bytes = create_owner_only_encrypted_pdf_bytes(owner_password="secretownerpass")
    pdf_path = os.path.join(input_dir, "restricted_statement.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    candidates = [{"name": "Random Client", "password": "ABCDE1234F"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})

    assert res["status"] == PDFUnlockStatus.UNLOCKED
    assert os.path.exists(res["output_path"])


def test_no_matching_password(temp_io_dirs):
    """Test return status when none of the candidate passwords match."""
    input_dir, output_dir = temp_io_dirs
    pdf_bytes = create_encrypted_pdf_bytes("SECRETPAN1")
    pdf_path = os.path.join(input_dir, "locked_report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    candidates = [{"name": "Wrong Client", "password": "WRONG1234F"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})

    assert res["status"] == PDFUnlockStatus.NO_MATCH
    assert res["output_path"] is None


def test_corrupted_pdf_handling(temp_io_dirs):
    """Test error status on corrupted / malformed PDF."""
    input_dir, output_dir = temp_io_dirs
    # Corrupt PDF header bytes
    pdf_path = os.path.join(input_dir, "corrupt.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\nCorrupt garbage content that pikepdf cannot parse")

    candidates = [{"name": "Client", "password": "ABCDE1234F"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})

    assert res["status"] == PDFUnlockStatus.ERROR
    assert "error" in res["error_message"].lower() or "corrupt" in res["error_message"].lower()


def test_empty_pdf_file_handling(temp_io_dirs):
    """Test error on 0 byte empty PDF file."""
    input_dir, output_dir = temp_io_dirs
    pdf_path = os.path.join(input_dir, "empty.pdf")
    with open(pdf_path, "wb") as f:
        pass  # 0 bytes

    candidates = [{"name": "Client", "password": "ABCDE1234F"}]
    res = attempt_unlock_pdf(pdf_path, output_dir, candidates, {})

    assert res["status"] == PDFUnlockStatus.ERROR
    assert "empty" in res["error_message"].lower()


def test_output_filename_generation():
    """Verify output filename conventions."""
    fn1 = generate_output_filename("Report.pdf", "Amit Patel", "ABCDE1234F")
    assert fn1 == "Amit_Patel_1234_unlocked.pdf"

    fn2 = generate_output_filename("Quarterly_Report_2026.pdf", None, None)
    assert fn2 == "Quarterly_Report_2026_unlocked.pdf"
