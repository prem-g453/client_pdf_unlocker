"""Generate demo files (Excel master + encrypted sample PDFs) for manual & browser testing."""
import os
import openpyxl
import pikepdf

DEMO_DIR = "demo_assets"
os.makedirs(DEMO_DIR, exist_ok=True)

# 1. Create Demo Excel
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Client Master"
ws.append(["Client Name", "PAN Number"])
ws.append(["John Doe", "ABCDE1234F"])
ws.append(["Priya Sharma", "BKRPK7654M"])
ws.append(["Amit Verma", "ZYXWV9876A"])
ws.append(["Non-PAN User", "CustomPass@2026"])  # For testing allow_non_pan toggle
ws.append(["Invalid PAN Test", "1234INVALID"])  # Triggers warning
ws.append(["", ""])  # Blank row (should be ignored)

excel_path = os.path.join(DEMO_DIR, "demo_clients.xlsx")
wb.save(excel_path)
print(f"Created: {excel_path}")

# 2. Create John Doe Encrypted PDF
pdf1 = pikepdf.new()
pdf1.add_blank_page()
pdf1_path = os.path.join(DEMO_DIR, "John_Doe_Portfolio_2026.pdf")
pdf1.save(
    pdf1_path,
    encryption=pikepdf.Encryption(
        user="ABCDE1234F",
        owner="owner_abcde1234f",
        R=6
    )
)
print(f"Created: {pdf1_path}")

# 3. Create Priya Sharma Encrypted PDF (encrypted with lowercase PAN to test case-insensitivity)
pdf2 = pikepdf.new()
pdf2.add_blank_page()
pdf2_path = os.path.join(DEMO_DIR, "Priya_Sharma_Statement.pdf")
pdf2.save(
    pdf2_path,
    encryption=pikepdf.Encryption(
        user="bkrpk7654m",  # lowercase
        owner="owner_bkrpk7654m",
        R=6
    )
)
print(f"Created: {pdf2_path}")

# 4. Create Already Unlocked PDF
pdf3 = pikepdf.new()
pdf3.add_blank_page()
pdf3_path = os.path.join(DEMO_DIR, "Public_Market_Summary.pdf")
pdf3.save(pdf3_path)
print(f"Created: {pdf3_path}")

# 5. Create Unknown / Locked PDF (password not in Excel)
pdf4 = pikepdf.new()
pdf4.add_blank_page()
pdf4_path = os.path.join(DEMO_DIR, "Unknown_Client_Doc.pdf")
pdf4.save(
    pdf4_path,
    encryption=pikepdf.Encryption(
        user="UNKNOWN9999Z",
        owner="owner_unknown",
        R=6
    )
)
print(f"Created: {pdf4_path}")

print("Demo assets generation complete!")
