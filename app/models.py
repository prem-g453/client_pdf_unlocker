import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from app.database import Base


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(32), default="staff", nullable=False)  # 'admin' or 'staff'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utc_now, index=True, nullable=False)
    username = Column(String(64), index=True, nullable=False)
    job_id = Column(String(64), index=True, nullable=False)
    total_files = Column(Integer, default=0, nullable=False)
    unlocked_count = Column(Integer, default=0, nullable=False)
    already_unlocked_count = Column(Integer, default=0, nullable=False)
    no_match_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Float, default=0.0, nullable=False)
    
    # JSON string containing file summary without passwords:
    # [{"original_file": "...", "status": "UNLOCKED", "matched_client": "...", "output_file": "..."}]
    file_details_json = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AuditLog {self.id} job={self.job_id} user={self.username} files={self.total_files}>"
