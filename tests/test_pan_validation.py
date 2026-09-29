import pytest
from app.security import validate_pan_format, mask_password, sanitize_filename


def test_pan_regex_valid():
    """Verify standard 10-character Indian PAN cards: 5 letters, 4 numbers, 1 letter."""
    valid_pans = [
        "ABCDE1234F",
        "ZYXWV9876A",
        "BKRPK7654M",
        "abcde1234f",  # Lowercase should be recognized when trimmed/uppered
    ]
    for pan in valid_pans:
        assert validate_pan_format(pan.upper()) is True


def test_pan_regex_invalid():
    """Verify malformed PAN strings fail validation."""
    invalid_pans = [
        "ABCDE1234",      # 9 chars
        "ABCDE12345",     # 10 chars, all digits at end
        "12345ABCDE",     # inverted
        "ABCD12345F",     # 4 letters, 5 digits
        "ABCDE1234FG",    # 11 chars
        "",               # empty
        "   ",            # spaces
        "ABCDE-1234-F",   # hyphens
        "PAN1234567"
    ]
    for pan in invalid_pans:
        assert validate_pan_format(pan) is False


def test_mask_password():
    """Verify sensitive PANs and passwords are properly masked."""
    assert mask_password("ABCDE1234F") == "ABCDE****F"
    assert mask_password("secretpass123") == "se*********23"
    assert mask_password("123") == "****"
    assert mask_password("") == "****"
    assert mask_password(None) == "****"


def test_sanitize_filename():
    """Verify path traversal, dangerous characters and backslashes are sanitized."""
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\calc.exe") == "calc.exe"
    assert sanitize_filename("John Doe (Report) [2026].pdf") == "John Doe _Report_ _2026_.pdf"
    assert sanitize_filename("safe_file.pdf") == "safe_file.pdf"
    assert sanitize_filename("...hidden.pdf") == "hidden.pdf"
    assert sanitize_filename("") == "unnamed_file"
