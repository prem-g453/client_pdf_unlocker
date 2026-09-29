import io
import time
import pytest
from tests.conftest import (
    create_sample_excel_bytes,
    create_encrypted_pdf_bytes,
    create_unencrypted_pdf_bytes
)


def test_auth_and_role_permissions(client, staff_token, admin_token):
    """Test user login, role checks, and authorization boundaries."""
    # Test staff profile
    res_staff = client.get("/api/auth/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert res_staff.status_code == 200
    assert res_staff.json()["role"] == "staff"

    # Staff trying to access admin endpoint -> 403 Forbidden
    res_forbidden = client.get("/api/admin/users", headers={"Authorization": f"Bearer {staff_token}"})
    assert res_forbidden.status_code == 403

    # Admin accessing admin endpoint -> 200 OK
    res_admin = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert len(res_admin.json()) >= 2


def test_excel_validation_endpoint(client, staff_token):
    """Test /api/unlock/validate-excel endpoint."""
    excel_bytes = create_sample_excel_bytes(
        rows=[
            ["John Doe", "ABCDE1234F"],
            ["Invalid User", "INVALID123"]
        ],
        header=["Name", "PAN"]
    )

    files = {"excel_file": ("clients.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"allow_non_pan": "false"}

    res = client.post(
        "/api/unlock/validate-excel",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {staff_token}"}
    )

    assert res.status_code == 200
    resp_data = res.json()
    assert resp_data["valid_count"] == 1
    assert resp_data["warning_count"] == 1


def test_end_to_end_unlock_job_flow(client, staff_token, admin_token):
    """
    Test full end-to-end API flow:
    1. Upload Excel + 2 Encrypted PDFs + 1 Unencrypted PDF
    2. Start job
    3. Poll job status until complete
    4. Download individual unlocked PDF
    5. Download ZIP
    6. Download CSV Report
    7. Admin checks Audit Log
    """
    pan1 = "ABCDE1234F"
    pan2 = "ZYXWV9876A"

    excel_bytes = create_sample_excel_bytes([
        ["Alice Smith", pan1],
        ["Bob Jones", pan2]
    ])

    pdf1_bytes = create_encrypted_pdf_bytes(pan1)
    pdf2_bytes = create_encrypted_pdf_bytes(pan2)
    pdf3_bytes = create_unencrypted_pdf_bytes()

    # Upload files
    files = [
        ("excel_file", ("clients.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ("pdf_files", ("Alice_Smith_Report.pdf", pdf1_bytes, "application/pdf")),
        ("pdf_files", ("Bob_Jones_Statement.pdf", pdf2_bytes, "application/pdf")),
        ("pdf_files", ("Public_Notice.pdf", pdf3_bytes, "application/pdf"))
    ]

    res_start = client.post(
        "/api/unlock/start",
        files=files,
        data={"allow_non_pan": "false"},
        headers={"Authorization": f"Bearer {staff_token}"}
    )

    assert res_start.status_code == 200
    job_id = res_start.json()["job_id"]
    assert job_id is not None

    # Poll status until completed (timeout 10 seconds)
    completed = False
    status_data = None
    for _ in range(20):
        res_status = client.get(
            f"/api/unlock/jobs/{job_id}/status",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert res_status.status_code == 200
        status_data = res_status.json()
        if status_data["is_completed"]:
            completed = True
            break
        time.sleep(0.5)

    assert completed is True
    assert status_data["unlocked_count"] == 2
    assert status_data["already_unlocked_count"] == 1
    assert status_data["no_match_count"] == 0
    assert status_data["error_count"] == 0

    # Test downloading individual unlocked file
    first_result = status_data["results"][0]
    res_dl = client.get(
        f"/api/unlock/jobs/{job_id}/download/{first_result['file_id']}",
        headers={"Authorization": f"Bearer {staff_token}"}
    )
    assert res_dl.status_code == 200
    assert res_dl.headers["content-type"] == "application/pdf"

    # Test downloading CSV report
    res_csv = client.get(
        f"/api/unlock/jobs/{job_id}/report.csv",
        headers={"Authorization": f"Bearer {staff_token}"}
    )
    assert res_csv.status_code == 200
    assert "Original File Name" in res_csv.text

    # Test downloading ZIP (and verify trigger cleanup)
    res_zip = client.get(
        f"/api/unlock/jobs/{job_id}/download-all",
        headers={"Authorization": f"Bearer {staff_token}"}
    )
    assert res_zip.status_code == 200
    assert res_zip.headers["content-type"] == "application/zip"

    # Admin verifies Audit Log
    res_audit = client.get(
        "/api/admin/audit-logs",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_audit.status_code == 200
    audit_items = res_audit.json()["items"]
    assert any(log["job_id"] == job_id for log in audit_items)
