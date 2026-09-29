import os
import time
import shutil
import asyncio
import logging
from app.config import get_settings
from app.services.job_manager import job_manager

settings = get_settings()
logger = logging.getLogger("pdf_unlocker.cleanup")


def cleanup_expired_jobs():
    """
    Scan temp directory and remove jobs older than RETENTION_MINUTES.
    Also clean up job_manager memory.
    """
    cutoff_time = time.time() - (settings.RETENTION_MINUTES * 60)
    temp_dir = settings.TEMP_DIR

    if not os.path.exists(temp_dir):
        return

    try:
        # Check directories on disk
        for entry in os.listdir(temp_dir):
            job_path = os.path.join(temp_dir, entry)
            if os.path.isdir(job_path):
                # Check directory creation/modification time
                mtime = os.path.getmtime(job_path)
                if mtime < cutoff_time:
                    try:
                        shutil.rmtree(job_path, ignore_errors=True)
                        logger.info(f"Cleaned up expired job directory on disk: {entry}")
                    except Exception as e:
                        logger.warning(f"Error removing expired job dir {entry}: {str(e)}")

        # Check in-memory jobs
        expired_ids = []
        for job_id, job in list(job_manager.jobs.items()):
            if job.created_at < cutoff_time:
                expired_ids.append(job_id)

        for j_id in expired_ids:
            job_manager.delete_job_files(j_id)
            logger.info(f"Purged expired job from memory: {j_id}")

    except Exception as e:
        logger.error(f"Error during job cleanup run: {str(e)}")


async def periodic_cleanup_task(interval_seconds: int = 300):
    """Background task running every 5 minutes."""
    while True:
        try:
            cleanup_expired_jobs()
        except Exception as e:
            logger.error(f"Exception in periodic cleanup task: {str(e)}")
        await asyncio.sleep(interval_seconds)
