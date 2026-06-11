#!/usr/bin/env python3
"""
Start both FastAPI backend and Streamlit frontend.
Usage:
    python start.py

Or run them separately:
    # Terminal 1 — Backend
    uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload

    # Terminal 2 — Frontend
    streamlit run frontend/app.py --server.port 8501
"""

import subprocess
import sys
import os
import signal
import time

def main():
    print("=" * 60)
    print("  DRHP Analyst Agent")
    print("  Starting backend + frontend...")
    print("=" * 60)

    # Check .env exists
    if not os.path.exists(".env"):
        print("\n⚠️  No .env file found. Creating from template...")
        import shutil
        shutil.copy(".env.example", ".env")
        print("   → Edit .env and add your GROQ_API_KEY\n")

    procs = []

    # Start FastAPI
    print("\n🚀 Starting FastAPI backend on http://localhost:8000")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    procs.append(backend)
    time.sleep(2)  # Let backend start

    # Start Streamlit
    print("🎨 Starting Streamlit frontend on http://localhost:8501")
    frontend = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "frontend/app.py",
         "--server.port", "8501", "--server.headless", "true"],
    )
    procs.append(frontend)

    print("\n" + "=" * 60)
    print("  ✅ Both servers running!")
    print("  📊 Frontend: http://localhost:8501")
    print("  🔧 API Docs:  http://localhost:8000/docs")
    print("  Press Ctrl+C to stop both")
    print("=" * 60 + "\n")

    def shutdown(sig, frame):
        print("\n🛑 Shutting down...")
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Stream backend logs
    while True:
        line = backend.stdout.readline()
        if line:
            print(f"[API] {line.decode().rstrip()}")
        if backend.poll() is not None:
            print("⚠️  Backend process stopped unexpectedly.")
            break
        time.sleep(0.01)


if __name__ == "__main__":
    main()
