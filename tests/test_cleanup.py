import os
import time
import tempfile
import pytest
from app.services.job_manager import JobManager
from app.services.cleanup_service import cleanup_expired_jobs
from app.config import get_settings

settings = get_settings()


def test_job_files_deletion():
    """Verify delete_job_files removes directory from disk and in-memory dict."""
    jm = JobManager()
    job = jm.create_job(username="test_user", total_files=1, candidates=[])
    
    base_dir = job.base_dir
    assert os.path.exists(base_dir)
    assert job.job_id in jm.jobs

    # Delete job
    jm.delete_job_files(job.job_id)

    assert not os.path.exists(base_dir)
    assert job.job_id not in jm.jobs


def test_cleanup_expired_jobs(monkeypatch):
    """Verify periodic cleanup removes folders older than retention minutes."""
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "TEMP_DIR", temp_dir)
    monkeypatch.setattr(settings, "RETENTION_MINUTES", 1)  # 1 minute

    old_job_dir = os.path.join(temp_dir, "old_job_123")
    os.makedirs(old_job_dir)
    # Set mtime back by 2 hours
    two_hours_ago = time.time() - 7200
    os.utime(old_job_dir, (two_hours_ago, two_hours_ago))

    fresh_job_dir = os.path.join(temp_dir, "fresh_job_456")
    os.makedirs(fresh_job_dir)

    cleanup_expired_jobs()

    assert not os.path.exists(old_job_dir)
    assert os.path.exists(fresh_job_dir)
