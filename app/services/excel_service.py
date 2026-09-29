import io
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
from openpyxl import load_workbook
from app.security import validate_pan_format, mask_password, validate_excel_content
from app.schemas import ExcelRowWarning, ExcelValidationResult


class ExcelProcessingError(Exception):
    pass


def parse_and_clean_excel(
    file_bytes: bytes,
    allow_non_pan: bool = False
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Parse uploaded Excel file (.xlsx or .xls), extract first two columns,
    clean and validate data according to business rules.

    Returns:
        valid_entries: List of dicts with {"name": str, "password": str, "is_valid_pan": bool, "masked_password": str}
        warnings: List of dicts with row warnings
        stats: Summary counts
    """
    if not file_bytes:
        raise ExcelProcessingError("Empty Excel file uploaded.")

    # Validate header magic bytes
    if not validate_excel_content(file_bytes[:8]):
        raise ExcelProcessingError("Invalid Excel file format. Please upload a valid .xlsx or .xls file.")

    try:
        # Read Excel using pandas
        # header=None so we can safely read first two columns regardless of header text
        df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine=None)
    except Exception as e:
        raise ExcelProcessingError(f"Could not read Excel file: {str(e)}")

    if df.empty or df.shape[1] < 2:
        raise ExcelProcessingError("Excel sheet must contain at least 2 columns (Client Name and Password/PAN).")

    # Select first two columns
    df = df.iloc[:, [0, 1]]
    df.columns = ["raw_name", "raw_password"]

    # Check if row 0 looks like a header (e.g. contains words like 'name', 'client', 'pan', 'password')
    start_row_idx = 0
    first_row_name = str(df.iloc[0, 0]).strip().lower()
    first_row_pwd = str(df.iloc[0, 1]).strip().lower()
    
    header_keywords = {"name", "client", "client name", "customer", "pan", "pancard", "password", "pwd", "pan card"}
    if first_row_name in header_keywords or first_row_pwd in header_keywords:
        start_row_idx = 1

    valid_entries: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    seen_names: Dict[str, int] = {}  # normalized name -> first row seen
    seen_client_pass_pairs = set()

    total_rows_read = 0

    for idx in range(start_row_idx, len(df)):
        row_num = idx + 1  # 1-indexed for user friendly display
        val_name = df.iloc[idx, 0]
        val_pwd = df.iloc[idx, 1]

        # Convert to stripped strings
        str_name = str(val_name).strip() if not pd.isna(val_name) else ""
        str_pwd = str(val_pwd).strip() if not pd.isna(val_pwd) else ""

        # Check for completely blank row (including whitespace only)
        if not str_name and not str_pwd:
            continue

        total_rows_read += 1

        # Check missing name
        if not str_name:
            warnings.append({
                "row_number": row_num,
                "client_name": "",
                "masked_password": mask_password(str_pwd) if str_pwd else "",
                "reason": "Missing client name",
                "action": "Skipped"
            })
            continue

        # Check missing password
        if not str_pwd:
            warnings.append({
                "row_number": row_num,
                "client_name": str_name,
                "masked_password": "",
                "reason": "Missing password/PAN",
                "action": "Skipped"
            })
            continue

        # Convert potential float representation (e.g. 12345.0) to clean string
        if isinstance(val_pwd, float) and val_pwd.is_integer():
            str_pwd = str(int(val_pwd)).strip()

        # PAN uppercase transformation
        upper_pwd = str_pwd.upper()
        is_pan = validate_pan_format(upper_pwd)

        # Non-PAN validation handling
        if not is_pan:
            if not allow_non_pan:
                warnings.append({
                    "row_number": row_num,
                    "client_name": str_name,
                    "masked_password": mask_password(str_pwd),
                    "reason": "Invalid PAN card format (expected ^[A-Z]{5}[0-9]{4}[A-Z]$)",
                    "action": "Skipped"
                })
                continue
            else:
                warnings.append({
                    "row_number": row_num,
                    "client_name": str_name,
                    "masked_password": mask_password(str_pwd),
                    "reason": "Non-standard PAN format (kept as non-PAN password)",
                    "action": "Kept as non-PAN"
                })
                # If non-PAN is allowed, keep the original casing or uppercase as candidate
                effective_password = str_pwd
        else:
            effective_password = upper_pwd

        # Duplicate checking
        norm_name = str_name.lower()
        pair_key = (norm_name, effective_password)

        if pair_key in seen_client_pass_pairs:
            warnings.append({
                "row_number": row_num,
                "client_name": str_name,
                "masked_password": mask_password(effective_password),
                "reason": f"Exact duplicate of row {seen_names.get(norm_name, 'earlier')}",
                "action": "Skipped duplicate"
            })
            continue

        if norm_name in seen_names:
            warnings.append({
                "row_number": row_num,
                "client_name": str_name,
                "masked_password": mask_password(effective_password),
                "reason": f"Duplicate client name (first seen on row {seen_names[norm_name]}) - using latest entry",
                "action": "Added"
            })

        seen_names[norm_name] = row_num
        seen_client_pass_pairs.add(pair_key)

        valid_entries.append({
            "name": str_name,
            "password": effective_password,
            "is_valid_pan": is_pan,
            "masked_password": mask_password(effective_password),
            "row_number": row_num
        })

    stats = {
        "total_rows_read": total_rows_read,
        "valid_count": len(valid_entries),
        "warning_count": len(warnings),
        "duplicate_count": sum(1 for w in warnings if "duplicate" in w["reason"].lower())
    }

    return valid_entries, warnings, stats
