import pytest
from tests.conftest import create_sample_excel_bytes
from app.services.excel_service import parse_and_clean_excel, ExcelProcessingError


def test_excel_clean_standard_columns():
    """Test reading Excel with standard headers, whitespace, and case conversions."""
    rows = [
        ["  Rohan Sharma  ", "  abcde1234f  "],
        ["Priya Patel", "BKRPK7654M"],
        ["Amit Kumar", "ZYXWV9876A"]
    ]
    excel_data = create_sample_excel_bytes(rows, header=["Client Name", "PAN Number"])
    
    valid_entries, warnings, stats = parse_and_clean_excel(excel_data, allow_non_pan=False)
    
    assert len(valid_entries) == 3
    assert stats["valid_count"] == 3
    assert stats["warning_count"] == 0
    assert valid_entries[0]["name"] == "Rohan Sharma"
    assert valid_entries[0]["password"] == "ABCDE1234F"  # Upper-cased
    assert valid_entries[0]["is_valid_pan"] is True


def test_excel_arbitrary_headers():
    """Test reading first 2 columns regardless of header names."""
    rows = [
        ["Rajesh Khanna", "ABCDE1234F"],
        ["Suresh Raina", "BKRPK7654M"]
    ]
    excel_data = create_sample_excel_bytes(rows, header=["Col Alpha 1", "Random Header 2"])
    
    valid_entries, warnings, stats = parse_and_clean_excel(excel_data, allow_non_pan=False)
    assert len(valid_entries) == 2


def test_excel_blank_rows_and_invalid_pan():
    """Test dropping blank rows and recording warnings for invalid PANs."""
    rows = [
        ["Valid Client", "ABCDE1234F"],
        [None, None],  # blank row (dropped)
        ["   ", "   "],  # whitespace blank row (dropped)
        ["Invalid PAN Client", "12345INVALID"],  # bad PAN
        ["Missing PAN Client", ""],  # missing password
        ["", "ABCDE1234F"]  # missing name
    ]
    excel_data = create_sample_excel_bytes(rows, header=["Customer", "PAN"])
    
    valid_entries, warnings, stats = parse_and_clean_excel(excel_data, allow_non_pan=False)
    
    assert len(valid_entries) == 1
    assert valid_entries[0]["name"] == "Valid Client"
    assert stats["warning_count"] == 3  # 3 invalid rows recorded as warnings
    
    warning_reasons = [w["reason"] for w in warnings]
    assert any("Invalid PAN card format" in r for r in warning_reasons)
    assert any("Missing password" in r for r in warning_reasons)
    assert any("Missing client name" in r for r in warning_reasons)


def test_excel_allow_non_pan_passwords():
    """Test keeping non-PAN passwords when allow_non_pan=True."""
    rows = [
        ["User One", "ABCDE1234F"],
        ["User Non PAN", "MySecretPass!2026"],
        ["User Number Only", "98765432"]
    ]
    excel_data = create_sample_excel_bytes(rows, header=["Name", "Password"])
    
    # When allow_non_pan=False, only 1 valid
    valid_1, warn_1, _ = parse_and_clean_excel(excel_data, allow_non_pan=False)
    assert len(valid_1) == 1

    # When allow_non_pan=True, all 3 are kept
    valid_2, warn_2, _ = parse_and_clean_excel(excel_data, allow_non_pan=True)
    assert len(valid_2) == 3
    assert valid_2[1]["password"] == "MySecretPass!2026"
    assert valid_2[1]["is_valid_pan"] is False


def test_excel_duplicate_detection():
    """Test duplicate detection in Excel rows."""
    rows = [
        ["Client A", "ABCDE1234F"],
        ["Client A", "ABCDE1234F"],  # Exact duplicate
        ["Client B", "ZYXWV9876A"]
    ]
    excel_data = create_sample_excel_bytes(rows)
    valid_entries, warnings, stats = parse_and_clean_excel(excel_data)
    
    assert len(valid_entries) == 2
    assert any("duplicate" in w["reason"].lower() for w in warnings)


def test_excel_invalid_format():
    """Test error when uploading invalid non-Excel bytes."""
    with pytest.raises(ExcelProcessingError):
        parse_and_clean_excel(b"Not an excel file content")
