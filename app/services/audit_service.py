import json
import csv
import io
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import AuditLog
from app.schemas import AuditLogResponse, AuditLogListResponse


def record_audit_log(
    db: Session,
    username: str,
    job_id: str,
    total_files: int,
    unlocked_count: int,
    already_unlocked_count: int,
    no_match_count: int,
    error_count: int,
    duration_seconds: float,
    file_results: List[Dict[str, Any]]
) -> AuditLog:
    """
    Save audit log entry.
    Ensures that NO passwords are recorded in file_results or anywhere in DB.
    """
    # Sanitize file results for audit log (strip any password references)
    sanitized_details = []
    for r in file_results:
        sanitized_details.append({
            "original_file": r.get("original_filename"),
            "output_file": r.get("output_filename"),
            "status": r.get("status"),
            "matched_client": r.get("matched_client"),
            "error_message": r.get("error_message")
        })

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    audit_entry = AuditLog(
        timestamp=now_utc,
        username=username,
        job_id=job_id,
        total_files=total_files,
        unlocked_count=unlocked_count,
        already_unlocked_count=already_unlocked_count,
        no_match_count=no_match_count,
        error_count=error_count,
        duration_seconds=round(duration_seconds, 2),
        file_details_json=json.dumps(sanitized_details)
    )

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def get_audit_logs(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    username: Optional[str] = None
) -> AuditLogListResponse:
    """Retrieve paginated audit logs."""
    query = db.query(AuditLog)
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username}%"))

    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(page_size).all()

    items = []
    for rec in records:
        details = None
        if rec.file_details_json:
            try:
                details = json.loads(rec.file_details_json)
            except Exception:
                details = []

        items.append(AuditLogResponse(
            id=rec.id,
            timestamp=rec.timestamp,
            username=rec.username,
            job_id=rec.job_id,
            total_files=rec.total_files,
            unlocked_count=rec.unlocked_count,
            already_unlocked_count=rec.already_unlocked_count,
            no_match_count=rec.no_match_count,
            error_count=rec.error_count,
            duration_seconds=rec.duration_seconds,
            file_details=details
        ))

    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )


def export_audit_logs_csv(db: Session) -> str:
    """Generate CSV string of all audit log records (NO PASSWORDS)."""
    records = db.query(AuditLog).order_by(desc(AuditLog.timestamp)).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Log ID",
        "Timestamp (UTC)",
        "User",
        "Job ID",
        "Total Files",
        "Unlocked",
        "Already Unlocked",
        "No Match",
        "Errors",
        "Duration (s)"
    ])

    for r in records:
        writer.writerow([
            r.id,
            r.timestamp.isoformat(),
            r.username,
            r.job_id,
            r.total_files,
            r.unlocked_count,
            r.already_unlocked_count,
            r.no_match_count,
            r.error_count,
            r.duration_seconds
        ])

    return output.getvalue()
