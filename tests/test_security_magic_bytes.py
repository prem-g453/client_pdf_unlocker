import pytest
from app.security import validate_pdf_content, validate_excel_content
from app.services.job_manager import JobManager
from app.services.audit_service import record_audit_log, export_audit_logs_csv
from tests.conftest import create_sample_excel_bytes


def test_pdf_magic_bytes_detection():
    """Verify %PDF- magic byte validation."""
    valid_pdf_header = b"%PDF-1.7\n\r"
    invalid_header_1 = b"MZ\x90\x00"  # Windows executable
    invalid_header_2 = b"PK\x03\x04"  # ZIP file
    invalid_header_3 = b"<html><head>"

    assert validate_pdf_content(valid_pdf_header) is True
    assert validate_pdf_content(invalid_header_1) is False
    assert validate_pdf_content(invalid_header_2) is False
    assert validate_pdf_content(invalid_header_3) is False


def test_excel_magic_bytes_detection():
    """Verify Excel XLSX (ZIP) and XLS (OLE) magic byte validation."""
    xlsx_bytes = create_sample_excel_bytes([["Test", "ABCDE1234F"]])
    assert validate_excel_content(xlsx_bytes[:8]) is True

    fake_excel = b"Plain text disguised as xlsx"
    assert validate_excel_content(fake_excel[:8]) is False


def test_no_passwords_in_audit_and_csv_reports(db_session):
    """Critical security test: Ensure PAN/passwords NEVER appear in audit logs or CSV reports."""
    jm = JobManager()
    job = jm.create_job(
        username="test_staff",
        total_files=2,
        candidates=[{"name": "Secret Client", "password": "SUPERSECRETPAN1"}]
    )

    # Simulate completed file results
    job.results = [
        {
            "file_id": "f1",
            "original_filename": "Client_Report.pdf",
            "output_filename": "Secret_Client_EPAN1_unlocked.pdf",
            "status": "Unlocked",
            "matched_client": "Secret Client",
            "error_message": None,
            "output_path": "/tmp/test.pdf"
        }
    ]

    # Check generated CSV report
    csv_report = jm.generate_csv_report(job.job_id)
    assert "SUPERSECRETPAN1" not in csv_report
    assert "Secret Client" in csv_report

    # Check Audit Log in DB
    audit_rec = record_audit_log(
        db=db_session,
        username="test_staff",
        job_id=job.job_id,
        total_files=1,
        unlocked_count=1,
        already_unlocked_count=0,
        no_match_count=0,
        error_count=0,
        duration_seconds=1.5,
        file_results=job.results
    )

    assert "SUPERSECRETPAN1" not in str(audit_rec.file_details_json)

    # Check exported audit CSV
    audit_csv = export_audit_logs_csv(db_session)
    assert "SUPERSECRETPAN1" not in audit_csv
