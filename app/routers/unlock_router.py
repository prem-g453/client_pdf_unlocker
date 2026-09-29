import os
import uuid
import json
import asyncio
from typing import List, Optional
from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File, Form,
    BackgroundTasks, Request
)
from fastapi.responses import StreamingResponse, FileResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings
from app.models import User
from app.auth import get_current_user, require_staff_or_admin
from app.security import (
    validate_excel_content, validate_pdf_content, sanitize_filename
)
from app.services.excel_service import parse_and_clean_excel, ExcelProcessingError
from app.services.job_manager import job_manager
from app.schemas import ExcelValidationResult, JobStatusResponse

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/unlock", tags=["PDF Unlocker"])


@router.post("/validate-excel", response_model=ExcelValidationResult)
async def validate_excel_endpoint(
    excel_file: UploadFile = File(...),
    allow_non_pan: bool = Form(False),
    current_user: User = Depends(require_staff_or_admin)
):
    """
    Validate uploaded Excel sheet without starting an unlock job.
    Returns cleaned counts, warnings, and masked previews.
    """
    content = await excel_file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel file exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB."
        )

    try:
        valid_entries, warnings, stats = parse_and_clean_excel(content, allow_non_pan=allow_non_pan)
    except ExcelProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Return masked preview of first 10 entries for UI
    preview = []
    for entry in valid_entries[:10]:
        preview.append({
            "row": entry.get("row_number"),
            "name": entry.get("name"),
            "masked_password": entry.get("masked_password"),
            "is_valid_pan": entry.get("is_valid_pan")
        })

    return ExcelValidationResult(
        total_rows_read=stats["total_rows_read"],
        valid_count=stats["valid_count"],
        warning_count=stats["warning_count"],
        duplicate_count=stats["duplicate_count"],
        warnings=warnings,
        preview_entries=preview
    )


@router.post("/start")
@limiter.limit(settings.RATE_LIMIT_UNLOCK)
async def start_unlock_job(
    request: Request,
    excel_file: UploadFile = File(...),
    pdf_files: List[UploadFile] = File(...),
    allow_non_pan: bool = Form(False),
    current_user: User = Depends(require_staff_or_admin)
):
    """
    Start a new batch PDF unlock job.
    Uploads 1 Excel file and up to 500 PDF files.
    """
    # 1. Validate file counts
    if not pdf_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select at least one PDF file to unlock."
        )

    if len(pdf_files) > settings.MAX_FILES_PER_JOB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot upload more than {settings.MAX_FILES_PER_JOB} PDF files per job."
        )

    # 2. Validate and parse Excel
    excel_bytes = await excel_file.read()
    if len(excel_bytes) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel file exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB."
        )

    try:
        valid_entries, warnings, stats = parse_and_clean_excel(excel_bytes, allow_non_pan=allow_non_pan)
    except ExcelProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel error: {str(e)}"
        )

    if not valid_entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid client password entries found in the Excel file."
        )

    # 3. Initialize Job
    job = job_manager.create_job(
        username=current_user.username,
        total_files=len(pdf_files),
        candidates=valid_entries
    )

    # 4. Stream & validate uploaded PDFs to disk (to avoid holding 500 files in RAM)
    for upload in pdf_files:
        file_id = uuid.uuid4().hex[:8]
        safe_orig_name = sanitize_filename(upload.filename or f"document_{file_id}.pdf")
        
        # Save directly to disk
        dest_filename = f"{file_id}_{safe_orig_name}"
        dest_path = os.path.join(job.input_dir, dest_filename)

        file_size = 0
        header_bytes = b""
        
        with open(dest_path, "wb") as f_out:
            while chunk := await upload.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > settings.max_file_size_bytes:
                    job_manager.delete_job_files(job.job_id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File '{safe_orig_name}' exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB."
                    )
                if len(header_bytes) < 8:
                    header_bytes += chunk[:8 - len(header_bytes)]
                f_out.write(chunk)

        # Basic magic byte check for early rejection
        if not validate_pdf_content(header_bytes):
            # Still record file item so it shows as Error in report
            pass

        job.file_items.append({
            "file_id": file_id,
            "input_path": dest_path,
            "original_filename": safe_orig_name
        })

    # 5. Launch processing in background
    asyncio.create_task(job_manager.start_job_processing(job.job_id))

    return {
        "job_id": job.job_id,
        "total_files": len(job.file_items),
        "status": "processing",
        "valid_client_count": len(valid_entries),
        "excel_warnings_count": len(warnings)
    }


@router.get("/jobs/{job_id}/progress")
async def stream_job_progress(
    job_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Server-Sent Events (SSE) endpoint to stream live job progress.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        q = job.add_event_listener()
        try:
            # Send initial state immediately
            init_data = json.dumps(job.to_status_response().model_dump())
            yield f"event: status\ndata: {init_data}\n\n"

            if job.status in ["completed", "failed"]:
                return

            while True:
                # Wait for next event
                msg = await q.get()
                event_type = msg.get("event", "message")
                data_str = json.dumps(msg.get("data", {}))
                yield f"event: {event_type}\ndata: {data_str}\n\n"

                if event_type == "complete":
                    break
        finally:
            job.remove_event_listener(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get current status and processed results for a job (polling fallback)."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job.to_status_response()


@router.get("/jobs/{job_id}/download/{file_id}")
async def download_single_file(
    job_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    """Download an individual unlocked PDF."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    # Find the result item
    matched_result = next((r for r in job.results if r["file_id"] == file_id), None)
    if not matched_result or not matched_result.get("output_path"):
        raise HTTPException(status_code=404, detail="Unlocked file not found or not ready.")

    file_path = matched_result["output_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File is no longer available on disk.")

    download_name = matched_result.get("output_filename") or os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=download_name
    )


@router.get("/jobs/{job_id}/download-all")
async def download_all_zip(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Download all unlocked PDFs as a single ZIP archive.
    Triggers cleanup of temp files once downloaded.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    zip_path = job_manager.generate_zip_archive(job_id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=400, detail="No unlocked files available to download.")

    # Schedule cleanup of job files after ZIP download completes
    background_tasks.add_task(job_manager.delete_job_files, job_id)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"unlocked_pdfs_{job_id[:8]}.zip"
    )


@router.get("/jobs/{job_id}/report.csv")
async def download_csv_report(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Download CSV audit report for the job (contains NO passwords)."""
    csv_data = job_manager.generate_csv_report(job_id)
    if not csv_data:
        raise HTTPException(status_code=404, detail="Job report not found.")

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=unlock_report_{job_id[:8]}.csv"
        }
    )
