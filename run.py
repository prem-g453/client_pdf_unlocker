"""
Client PDF Unlocker - Zero-Configuration Launcher
This script automatically checks dependencies, finds an open port,
launches the server, and opens the app in your default browser.
"""

import os
import sys
import time
import socket
import webbrowser
import threading
import subprocess


def check_and_install_dependencies():
    """Verify required packages and install if missing."""
    required = [
        "fastapi", "uvicorn", "pikepdf", "openpyxl",
        "pandas", "bcrypt", "jwt", "sqlalchemy",
        "pydantic", "pydantic_settings", "slowapi", "jinja2"
    ]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print("\n" + "=" * 60)
        print("  Installing required dependencies for first-time run...")
        print("=" * 60 + "\n")
        req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
        if os.path.exists(req_file):
            cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
        else:
            cmd = [sys.executable, "-m", "pip", "install", *missing]
        
        try:
            subprocess.check_call(cmd)
            print("\nDependencies installed successfully!\n")
        except subprocess.CalledProcessError as e:
            print(f"\nError installing dependencies: {e}")
            print("Please run: pip install -r requirements.txt")
            input("\nPress Enter to exit...")
            sys.exit(1)


def is_port_available(host: str, port: int) -> bool:
    """Check if a network port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.bind((host, port))
            return True
        except socket.error:
            return False


def find_free_port(host: str = "127.0.0.1", default_port: int = 8000) -> int:
    """Find an available port starting from default_port."""
    for port in range(default_port, default_port + 50):
        if is_port_available(host, port):
            return port
    return default_port


def open_browser(url: str, delay: float = 1.2):
    """Open default web browser after server starts."""
    time.sleep(delay)
    print(f"Opening browser at: {url}")
    webbrowser.open(url)


def main():
    print("\n" + "=" * 64)
    print("        CLIENT PDF UNLOCKER - SECURE LOCAL INSTANCE")
    print("=" * 64)

    # 1. Dependency check
    check_and_install_dependencies()

    # 2. Port check
    host = "127.0.0.1"
    port = find_free_port(host, 8000)

    # 3. Ensure demo assets exist for quick testing
    demo_script = os.path.join(os.path.dirname(__file__), "generate_demo_assets.py")
    if os.path.exists(demo_script) and not os.path.exists(os.path.join(os.path.dirname(__file__), "demo_assets")):
        try:
            subprocess.run([sys.executable, demo_script], check=False)
        except Exception:
            pass

    app_url = f"http://{host}:{port}"
    print(f"\nStarting application server on {app_url} ...")
    print("Default Staff Login:  staff / Staff@12345")
    print("Default Admin Login:  admin / Admin@12345")
    print("-" * 64)
    print("Press Ctrl + C in this window to stop the server anytime.\n")

    # 4. Open browser in a background thread
    threading.Thread(target=open_browser, args=(app_url,), daemon=True).start()

    # 5. Run uvicorn server
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nApplication stopped safely. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error starting application: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)
