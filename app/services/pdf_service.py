import os
import re
import shutil
from typing import List, Dict, Any, Optional, Tuple
import pikepdf
from app.security import validate_pdf_content, sanitize_filename


class PDFUnlockStatus:
    UNLOCKED = "Unlocked"
    ALREADY_UNLOCKED = "Already unlocked"
    NO_MATCH = "No matching password"
    ERROR = "Error"


def normalize_name_for_matching(name: str) -> str:
    """Normalize a name by removing spaces, underscores, and special chars, in lowercase."""
    if not name:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


def extract_last_4_pan_digits(pan_or_pwd: str) -> str:
    """Extract the last 4 digits of a PAN or last 4 characters of password."""
    if not pan_or_pwd:
        return "0000"
    pan = str(pan_or_pwd).strip()
    # Search for 4 consecutive digits (standard PAN format ABCDE1234F)
    match = re.search(r"[0-9]{4}", pan)
    if match:
        return match.group(0)
    # Fallback to last 4 characters or full string
    return pan[-4:] if len(pan) >= 4 else pan


def generate_output_filename(
    original_filename: str,
    client_name: Optional[str] = None,
    password_used: Optional[str] = None
) -> str:
    """
    Generate output filename following requirement:
    <client_name_pancardno_last 4 digits>_unlocked.pdf
    or <original_stem>_unlocked.pdf if no client matched.
    """
    if client_name and password_used:
        sanitized_client = sanitize_filename(client_name.replace(" ", "_"))
        last4 = extract_last_4_pan_digits(password_used)
        return f"{sanitized_client}_{last4}_unlocked.pdf"
    
    # Fallback using original filename stem
    orig_clean = sanitize_filename(original_filename)
    stem, _ = os.path.splitext(orig_clean)
    return f"{stem}_unlocked.pdf"


def get_prioritized_candidates(
    filename: str,
    candidates: List[Dict[str, Any]],
    session_cache: Dict[str, str]
) -> List[Tuple[str, str]]:
    """
    Build prioritized list of (client_name, candidate_password) pairs:
    1. Session cached winning passwords
    2. Candidates whose client name appears in the PDF filename (case-insensitive, ignoring spaces/underscores)
    3. All remaining candidate passwords from the Excel sheet.
    """
    normalized_filename = normalize_name_for_matching(filename)
    
    cached_candidates: List[Tuple[str, str]] = []
    name_matched_candidates: List[Tuple[str, str]] = []
    remaining_candidates: List[Tuple[str, str]] = []
    
    seen_passwords = set()

    # 1. First, check session cache
    for client_name, cached_pwd in session_cache.items():
        if cached_pwd not in seen_passwords:
            cached_candidates.append((client_name, cached_pwd))
            seen_passwords.add(cached_pwd)

    # 2. Check name matches in filename
    for entry in candidates:
        name = entry.get("name", "")
        pwd = entry.get("password", "")
        if not pwd or pwd in seen_passwords:
            continue
            
        norm_name = normalize_name_for_matching(name)
        if norm_name and (norm_name in normalized_filename or (len(norm_name) >= 4 and norm_name[:4] in normalized_filename)):
            name_matched_candidates.append((name, pwd))
            seen_passwords.add(pwd)

    # 3. Add all other candidates
    for entry in candidates:
        name = entry.get("name", "")
        pwd = entry.get("password", "")
        if not pwd or pwd in seen_passwords:
            continue
        remaining_candidates.append((name, pwd))
        seen_passwords.add(pwd)

    return cached_candidates + name_matched_candidates + remaining_candidates


def attempt_unlock_pdf(
    input_path: str,
    output_dir: str,
    candidates: List[Dict[str, Any]],
    session_cache: Dict[str, str]
) -> Dict[str, Any]:
    """
    Unlock a single PDF file against candidate passwords.
    
    Returns:
        {
            "status": PDFUnlockStatus,
            "matched_client": Optional[str],
            "output_filename": Optional[str],
            "output_path": Optional[str],
            "error_message": Optional[str],
            "password_found": Optional[str] # used internally for caching, never logged
        }
    """
    original_filename = os.path.basename(input_path)
    
    # 1. Check file existence & non-empty
    if not os.path.exists(input_path):
        return {
            "status": PDFUnlockStatus.ERROR,
            "matched_client": None,
            "output_filename": None,
            "output_path": None,
            "error_message": "File not found.",
            "password_found": None
        }
        
    file_size = os.path.getsize(input_path)
    if file_size == 0:
        return {
            "status": PDFUnlockStatus.ERROR,
            "matched_client": None,
            "output_filename": None,
            "output_path": None,
            "error_message": "Empty file (0 bytes).",
            "password_found": None
        }

    # 2. Validate PDF magic bytes
    try:
        with open(input_path, "rb") as f:
            header = f.read(8)
            if not validate_pdf_content(header):
                return {
                    "status": PDFUnlockStatus.ERROR,
                    "matched_client": None,
                    "output_filename": None,
                    "output_path": None,
                    "error_message": "Invalid PDF format (missing standard %PDF header).",
                    "password_found": None
                }
    except Exception as e:
        return {
            "status": PDFUnlockStatus.ERROR,
            "matched_client": None,
            "output_filename": None,
            "output_path": None,
            "error_message": f"Could not read file: {str(e)}",
            "password_found": None
        }

    # 3. Check if PDF is already unlocked or has owner-only password
    try:
        with pikepdf.open(input_path) as pdf:
            is_encrypted = getattr(pdf, "is_encrypted", False)
            
            # If not encrypted at all
            if not is_encrypted:
                out_filename = generate_output_filename(original_filename)
                out_path = os.path.join(output_dir, out_filename)
                # Ensure unique output name if collision
                out_path = _get_unique_path(out_path)
                out_filename = os.path.basename(out_path)
                
                shutil.copy2(input_path, out_path)
                return {
                    "status": PDFUnlockStatus.ALREADY_UNLOCKED,
                    "matched_client": None,
                    "output_filename": out_filename,
                    "output_path": out_path,
                    "error_message": None,
                    "password_found": None
                }
            else:
                # PDF was encrypted with Owner password only (no user password required to open)
                out_filename = generate_output_filename(original_filename)
                out_path = os.path.join(output_dir, out_filename)
                out_path = _get_unique_path(out_path)
                out_filename = os.path.basename(out_path)
                
                # pikepdf.save() automatically removes owner password / restrictions
                pdf.save(out_path)
                return {
                    "status": PDFUnlockStatus.UNLOCKED,
                    "matched_client": "Owner restrictions removed",
                    "output_filename": out_filename,
                    "output_path": out_path,
                    "error_message": None,
                    "password_found": None
                }

    except pikepdf.PasswordError:
        # File is user-password protected, proceed to password testing
        pass
    except pikepdf.PdfError as e:
        return {
            "status": PDFUnlockStatus.ERROR,
            "matched_client": None,
            "output_filename": None,
            "output_path": None,
            "error_message": f"Corrupted or unsupported PDF structure: {str(e)}",
            "password_found": None
        }
    except Exception as e:
        return {
            "status": PDFUnlockStatus.ERROR,
            "matched_client": None,
            "output_filename": None,
            "output_path": None,
            "error_message": f"Unexpected error reading PDF: {str(e)}",
            "password_found": None
        }

    # 4. Attempt password testing with prioritized candidate list
    prioritized = get_prioritized_candidates(original_filename, candidates, session_cache)
    
    for client_name, base_pwd in prioritized:
        # Generate variants: exact, uppercase, lowercase
        variants = []
        for v in [base_pwd, base_pwd.upper(), base_pwd.lower()]:
            if v not in variants:
                variants.append(v)

        for candidate_pwd in variants:
            try:
                with pikepdf.open(input_path, password=candidate_pwd) as pdf:
                    # Successfully opened! Save unlocked version
                    out_filename = generate_output_filename(original_filename, client_name, candidate_pwd)
                    out_path = os.path.join(output_dir, out_filename)
                    out_path = _get_unique_path(out_path)
                    out_filename = os.path.basename(out_path)
                    
                    pdf.save(out_path)
                    
                    # Update session cache for subsequent files
                    if client_name:
                        session_cache[client_name] = candidate_pwd
                        
                    return {
                        "status": PDFUnlockStatus.UNLOCKED,
                        "matched_client": client_name,
                        "output_filename": out_filename,
                        "output_path": out_path,
                        "error_message": None,
                        "password_found": candidate_pwd
                    }
            except pikepdf.PasswordError:
                # Password incorrect, continue to next
                continue
            except pikepdf.PdfError as e:
                # Corrupted stream/encryption issue
                return {
                    "status": PDFUnlockStatus.ERROR,
                    "matched_client": None,
                    "output_filename": None,
                    "output_path": None,
                    "error_message": f"PDF error during decryption: {str(e)}",
                    "password_found": None
                }
            except Exception as e:
                return {
                    "status": PDFUnlockStatus.ERROR,
                    "matched_client": None,
                    "output_filename": None,
                    "output_path": None,
                    "error_message": f"Decryption failure: {str(e)}",
                    "password_found": None
                }

    # All candidate passwords failed
    return {
        "status": PDFUnlockStatus.NO_MATCH,
        "matched_client": None,
        "output_filename": None,
        "output_path": None,
        "error_message": "No matching password found in uploaded client list.",
        "password_found": None
    }


def _get_unique_path(target_path: str) -> str:
    """If target_path exists, append numeric suffix to prevent overwrite."""
    if not os.path.exists(target_path):
        return target_path
        
    dirname, basename = os.path.split(target_path)
    stem, ext = os.path.splitext(basename)
    counter = 1
    
    while True:
        new_basename = f"{stem}_{counter}{ext}"
        new_path = os.path.join(dirname, new_basename)
        if not os.path.exists(new_path):
            return new_path
        counter += 1
