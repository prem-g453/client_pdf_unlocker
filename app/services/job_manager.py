import os
import io
import time
import uuid
import shutil
import zipfile
import csv
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, AsyncGenerator

from app.config import get_settings
from app import database
from app.services.pdf_service import attempt_unlock_pdf, PDFUnlockStatus
from app.services.audit_service import record_audit_log
from app.schemas import FileProcessResult, JobStatusResponse

settings = get_settings()


class Job:
    def __init__(self, job_id: str, username: str, total_files: int, candidates: List[Dict[str, Any]]):
        self.job_id = job_id
        self.username = username
        self.total_files = total_files
        # Candidates in RAM ONLY for the duration of the job
        self.candidates: Optional[List[Dict[str, Any]]] = candidates
        self.session_cache: Dict[str, str] = {}  # winning passwords cached during job
        
        self.status = "pending"  # "pending", "processing", "completed", "failed"
        self.processed_files = 0
        self.unlocked_count = 0
        self.already_unlocked_count = 0
        self.no_match_count = 0
        self.error_count = 0
        self.created_at = time.time()
        self.completed_at: Optional[float] = None
        
        self.results: List[Dict[str, Any]] = []
        self.file_items: List[Dict[str, str]] = []  # [{file_id, input_path, original_filename}]
        
        # SSE Queues for real-time subscribers
        self.event_queues: List[asyncio.Queue] = []
        
        # Directories
        self.base_dir = os.path.join(settings.TEMP_DIR, job_id)
        self.input_dir = os.path.join(self.base_dir, "inputs")
        self.output_dir = os.path.join(self.base_dir, "outputs")
        
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def duration(self) -> float:
        end = self.completed_at or time.time()
        return round(end - self.created_at, 2)

    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 100.0
        return round((self.processed_files / self.total_files) * 100.0, 1)

    def to_status_response(self) -> JobStatusResponse:
        results_formatted = []
        for r in self.results:
            dl_url = None
            if r.get("output_path") and os.path.exists(r["output_path"]):
                dl_url = f"/api/unlock/jobs/{self.job_id}/download/{r['file_id']}"
                
            results_formatted.append(FileProcessResult(
                file_id=r["file_id"],
                original_filename=r["original_filename"],
                output_filename=r.get("output_filename"),
                status=r["status"],
                matched_client=r.get("matched_client"),
                error_message=r.get("error_message"),
                download_url=dl_url
            ))

        # Generate helpful summary message
        summary = None
        if self.status in ["completed", "failed"]:
            success_count = self.unlocked_count + self.already_unlocked_count
            failed_total = self.no_match_count + self.error_count
            
            if failed_total == 0:
                summary = f"All {self.total_files} file(s) successfully processed and ready for download."
            elif success_count == 0:
                summary = f"None of the {self.total_files} file(s) could be unlocked. Please verify your Excel client list and passwords."
            else:
                summary = f"{success_count} unlocked, {failed_total} failed. (Failed files may be missing from the Excel sheet or have incorrect passwords)."

        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,
            total_files=self.total_files,
            processed_files=self.processed_files,
            unlocked_count=self.unlocked_count,
            already_unlocked_count=self.already_unlocked_count,
            no_match_count=self.no_match_count,
            error_count=self.error_count,
            percent_complete=self.percent_complete(),
            is_completed=(self.status in ["completed", "failed"]),
            results=results_formatted,
            created_at=self.created_at,
            duration_seconds=self.duration(),
            summary_message=summary
        )

    def add_event_listener(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.event_queues.append(q)
        return q

    def remove_event_listener(self, q: asyncio.Queue):
        if q in self.event_queues:
            self.event_queues.remove(q)

    def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        message = {"event": event_type, "data": data}
        for q in list(self.event_queues):
            try:
                q.put_nowait(message)
            except Exception:
                pass


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.executor = ThreadPoolExecutor(max_workers=settings.WORKER_COUNT)

    def create_job(
        self,
        username: str,
        total_files: int,
        candidates: List[Dict[str, Any]]
    ) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(job_id, username, total_files, candidates)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    async def start_job_processing(self, job_id: str):
        job = self.get_job(job_id)
        if not job:
            return

        job.status = "processing"
        job.broadcast_event("status", job.to_status_response().model_dump())

        # Process files concurrently with bounded concurrency
        loop = asyncio.get_running_loop()
        semaphore = asyncio.Semaphore(settings.WORKER_COUNT)

        async def _process_single_file(item: Dict[str, str]):
            async with semaphore:
                file_id = item["file_id"]
                input_path = item["input_path"]
                orig_name = item["original_filename"]

                # Run pikepdf unlock in threadpool
                unlock_res = await loop.run_in_executor(
                    self.executor,
                    attempt_unlock_pdf,
                    input_path,
                    job.output_dir,
                    job.candidates or [],
                    job.session_cache
                )

                # Update counters
                status = unlock_res["status"]
                if status == PDFUnlockStatus.UNLOCKED:
                    job.unlocked_count += 1
                elif status == PDFUnlockStatus.ALREADY_UNLOCKED:
                    job.already_unlocked_count += 1
                elif status == PDFUnlockStatus.NO_MATCH:
                    job.no_match_count += 1
                else:
                    job.error_count += 1

                job.processed_files += 1

                file_res = {
                    "file_id": file_id,
                    "original_filename": orig_name,
                    "output_filename": unlock_res.get("output_filename"),
                    "output_path": unlock_res.get("output_path"),
                    "status": status,
                    "matched_client": unlock_res.get("matched_client"),
                    "error_message": unlock_res.get("error_message")
                }
                job.results.append(file_res)

                # Broadcast progress item
                dl_url = None
                if unlock_res.get("output_path") and os.path.exists(unlock_res["output_path"]):
                    dl_url = f"/api/unlock/jobs/{job.job_id}/download/{file_id}"

                item_payload = {
                    "file_id": file_id,
                    "original_filename": orig_name,
                    "output_filename": unlock_res.get("output_filename"),
                    "status": status,
                    "matched_client": unlock_res.get("matched_client"),
                    "error_message": unlock_res.get("error_message"),
                    "download_url": dl_url,
                    "processed_files": job.processed_files,
                    "total_files": job.total_files,
                    "percent_complete": job.percent_complete(),
                    "unlocked_count": job.unlocked_count,
                    "already_unlocked_count": job.already_unlocked_count,
                    "no_match_count": job.no_match_count,
                    "error_count": job.error_count
                }
                job.broadcast_event("progress", item_payload)

        # Launch all file tasks
        tasks = [_process_single_file(item) for item in job.file_items]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Complete job
        job.status = "completed"
        job.completed_at = time.time()

        # CRITICAL SECURITY STEP: Wipe raw passwords from memory immediately!
        job.candidates = None
        job.session_cache.clear()

        # Record Audit Log in SQLite (no passwords!)
        try:
            with database.SessionLocal() as db:
                record_audit_log(
                    db=db,
                    username=job.username,
                    job_id=job.job_id,
                    total_files=job.total_files,
                    unlocked_count=job.unlocked_count,
                    already_unlocked_count=job.already_unlocked_count,
                    no_match_count=job.no_match_count,
                    error_count=job.error_count,
                    duration_seconds=job.duration(),
                    file_results=job.results
                )
        except Exception as e:
            # Audit log failure shouldn't crash app, but should be handled
            pass

        # Final broadcast
        job.broadcast_event("complete", job.to_status_response().model_dump())

    def generate_csv_report(self, job_id: str) -> Optional[str]:
        """Generate CSV string of job results without passwords."""
        job = self.get_job(job_id)
        if not job:
            return None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Original File Name",
            "Output File Name",
            "Status",
            "Matched Client",
            "Error Details",
            "Processed At (Job ID)"
        ])

        for r in job.results:
            writer.writerow([
                r.get("original_filename", ""),
                r.get("output_filename", "") or "N/A",
                r.get("status", ""),
                r.get("matched_client", "") or "N/A",
                r.get("error_message", "") or "",
                job.job_id
            ])

        return output.getvalue()

    def generate_zip_archive(self, job_id: str) -> Optional[str]:
        """
        Generate a ZIP file containing all unlocked/decrypted PDFs and the CSV summary report.
        Returns the path to the created zip file.
        """
        job = self.get_job(job_id)
        if not job or not os.path.exists(job.output_dir):
            return None

        zip_filename = f"unlocked_pdfs_{job_id[:8]}.zip"
        zip_path = os.path.join(job.base_dir, zip_filename)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add all output PDFs
            for r in job.results:
                out_path = r.get("output_path")
                out_name = r.get("output_filename")
                if out_path and os.path.exists(out_path):
                    zf.write(out_path, arcname=out_name or os.path.basename(out_path))

            # Add CSV report to ZIP
            csv_content = self.generate_csv_report(job_id)
            if csv_content:
                zf.writestr("unlock_summary_report.csv", csv_content)

        return zip_path

    def delete_job_files(self, job_id: str):
        """Immediately delete all temporary files for a job."""
        job = self.get_job(job_id)
        base_dir = os.path.join(settings.TEMP_DIR, job_id)
        if os.path.exists(base_dir):
            try:
                shutil.rmtree(base_dir, ignore_errors=True)
            except Exception:
                pass
        
        # Remove from in-memory dict
        if job_id in self.jobs:
            # Clear remaining data
            self.jobs[job_id].candidates = None
            self.jobs[job_id].session_cache.clear()
            self.jobs.pop(job_id, None)


# Global singleton job manager
job_manager = JobManager()
