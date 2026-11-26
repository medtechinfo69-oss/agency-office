"""Container entrypoint: one worker and persistent storage for SQLite/jobs."""
import os
from pathlib import Path


def main():
    data = Path(os.environ.get("DATA_DIR", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    if os.getuid() == 0:
        # Mounted disks can initially be root-owned. Existing app files are
        # already owned by this fixed UID; no recursive ownership changes.
        os.chown(data, 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    os.execvp("uvicorn", [
        "uvicorn", "app.main:app", "--host", "0.0.0.0",
        "--port", os.environ.get("PORT", "10000"), "--workers", "1",
    ])


if __name__ == "__main__":
    main()
