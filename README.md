# Client PDF Unlocker

An enterprise internal web application designed for portfolio management teams to bulk unlock password-protected client portfolio PDF reports using PAN card numbers provided via Excel sheets.

---

## ⚡ Zero-Configuration Local Run (For Clients / Non-Technical Users)

You can share this folder directly with your clients or staff without setting up cloud servers or complex configurations:

### Option A: Windows (Double-Click Launcher)
1. Double-click **[`run_app.bat`](file:///c:/Users/Prem/Documents/client_pdf_unlocker/run_app.bat)**.
2. The launcher will automatically set up the virtual environment, install dependencies, start the local server, and **pop open the app in your default browser** (`http://127.0.0.1:8000`).
3. *(Optional)* Double-click **[`setup_desktop_shortcut.bat`](file:///c:/Users/Prem/Documents/client_pdf_unlocker/setup_desktop_shortcut.bat)** to create a convenient **"Client PDF Unlocker"** desktop icon.

### Option B: macOS / Linux
Run the shell script:
```bash
chmod +x run_app.sh
./run_app.sh
```

### Option C: Universal Python Command
```bash
python run.py
```
*(This automatically detects an open port, launches the backend, and opens the browser).*

---

## 🔑 Default Credentials
- **Staff Login:** `staff` / `Staff@12345` (Can upload Excel & decrypt PDFs)
- **Admin Login:** `admin` / `Admin@12345` (Can manage users & inspect audit logs)

---

## 🌟 Key Features

1. **Intelligent Password Matching & Decryption:**
   - **Name Match Prioritization:** Automatically detects client names in PDF filenames (ignoring case, spaces, and underscores) and tries their passwords first.
   - **Case Permutations:** Automatically tests exact, uppercase, and lowercase variants of passwords.
   - **Session Cache:** Caches winning client passwords in memory to accelerate subsequent PDF decryptions.
   - **Owner-only & Unencrypted Support:** Automatically detects already unlocked files and strips owner-password restrictions without errors.
   - **Parallel Processing:** Multi-worker processing pool with real-time Server-Sent Events (SSE) progress streaming.

2. **Excel Ingestion & Validation:**
   - Reads the first two columns regardless of custom headers.
   - Strips whitespace, drops empty rows, and converts PANs to uppercase.
   - Strict Indian PAN validation (`^[A-Z]{5}[0-9]{4}[A-Z]$`) with duplicate and error warnings.
   - Option to "Allow non-PAN passwords" for custom passcodes.

3. **Enterprise-Grade Security & PAN Privacy:**
   - **RAM-Only Credentials:** Client passwords and PANs live in volatile memory *only* for the active duration of the decryption job. They are **never** written to disk, SQLite database, logs, URLs, or error traces.
   - **Masked Displays:** Passwords and PANs are masked (`ABCDE****F` or `****`) in all API responses and UI components.
   - **Automatic Cleanup:** Uploads and decrypted PDFs are stored under isolated random UUID job directories and deleted after 30 minutes or immediately following a ZIP download.
   - **Upload Hardening:** Validates file magic bytes (`%PDF-`, `PK\x03\x04`, `\xd0\xcf\x11\xe0`), enforces a 50MB per-file limit (up to 500 PDFs per job), and sanitizes filenames against path traversal (`../../`).
   - **Role-Based Access Control:** Built-in authentication (Bcrypt hashing, 30-minute JWT session expiration) separating `Admin` and `Staff` roles.
   - **Zero-Leak Audit Trail:** SQLite audit logs track timestamps, usernames, file counts, and success statuses—strictly omitting passwords.

4. **Modern, Responsive Web Interface:**
   - Dark slate financial dashboard aesthetic with glassmorphism panels.
   - 3-step wizard with drag-and-drop file uploaders.
   - Real-time animated progress bar, live metrics counter, filterable results table, single file downloads, batch ZIP download, and CSV audit report export.

---

## 🚀 Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Pydantic v2, SlowAPI
- **Decryption Engine:** `pikepdf` (QPDF C++ backend)
- **Data Ingestion:** `openpyxl`, `pandas`
- **Database:** SQLite
- **Security:** `bcrypt`, `pyjwt`
- **Frontend:** Vanilla JS, Tailwind CSS, Server-Sent Events (SSE)
- **Deployment:** Docker, Docker Compose, Nginx / Caddy reverse proxy

---

## 📁 Project Structure

```
client_pdf_unlocker/
├── run.py                     # Zero-configuration python launcher
├── run_app.bat                # Windows 1-click double-click launcher
├── run_app.sh                 # macOS/Linux 1-click launcher
├── setup_desktop_shortcut.bat # Creates a desktop shortcut on Windows
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app initialization, middleware, lifespan
│   ├── config.py              # Pydantic Settings & environment variables
│   ├── database.py            # SQLite & SQLAlchemy engine
│   ├── models.py              # User & AuditLog ORM models
│   ├── schemas.py             # Pydantic request/response schemas
│   ├── auth.py                # Authentication dependencies & RBAC
│   ├── security.py            # Bcrypt hashing, JWT, PAN validation & masking
│   ├── services/
│   │   ├── __init__.py
│   │   ├── excel_service.py   # Excel parsing, whitespace trimming, PAN checks
│   │   ├── pdf_service.py     # Pikepdf decryption, prioritization & caching
│   │   ├── job_manager.py     # Parallel execution, SSE streams, ZIP/CSV export
│   │   ├── audit_service.py   # Secure audit trail logging (no passwords)
│   │   └── cleanup_service.py # Periodic temp job file cleanup
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth_router.py     # Login, profile, logout endpoints
│   │   ├── unlock_router.py   # Excel/PDF uploads, SSE stream, downloads
│   │   └── admin_router.py    # User management & audit logs
│   ├── static/
│   │   ├── css/style.css      # Dark glassmorphism styling
│   │   └── js/app.js          # SPA frontend logic & SSE subscriber
│   └── templates/
│       └── index.html         # Single-page UI
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Test database & PDF/Excel generator fixtures
│   ├── test_pan_validation.py # PAN format regex & masking tests
│   ├── test_excel_service.py  # Excel cleaning & header tests
│   ├── test_pdf_unlock.py     # Pikepdf decryption, owner-only, & corrupt tests
│   ├── test_security_magic_bytes.py # Magic bytes & zero-leak verification
│   ├── test_cleanup.py        # Disk & memory cleanup tests
│   └── test_api_flow.py       # Full end-to-end API integration tests
├── Dockerfile
├── docker-compose.yml
├── nginx.conf                 # Hardened Nginx configuration (HTTPS + Rate Limits)
├── Caddyfile                  # Automatic TLS Caddy configuration
├── requirements.txt
├── .env.example
├── .env
└── README.md
```

---

## 🧪 Running Unit & Integration Tests

Run the complete test suite with `pytest`:
```bash
python -m pytest tests/ -v
```

All 27 automated tests cover:
- PAN regex validation, casing, and masking
- Excel header independence, blank row skipping, and non-PAN allowances
- Decryption of sample encrypted PDFs generated on-the-fly
- Name-matched prioritization order
- Pass-through of already-unlocked and owner-only restricted PDFs
- Corrupted and empty PDF edge cases
- File magic bytes verification & path traversal sanitization
- Periodic and post-download temp file cleanup
- Full end-to-end API lifecycle and zero-password audit logs
