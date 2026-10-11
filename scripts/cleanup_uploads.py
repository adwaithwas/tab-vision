"""Remove stored uploads older than the configured retention window.

Usage (from the repository root, using the backend virtual environment)::

    backend\\.venv\\Scripts\\python.exe scripts\\cleanup_uploads.py
    backend\\.venv\\Scripts\\python.exe scripts\\cleanup_uploads.py --dry-run

Only files inside the configured upload directory are touched; every path is
resolved and checked to stay inside that directory. Set ``GUITARTAB_KEEP_UPLOADS_DAYS=0``
(and pass ``--all``) to remove everything regardless of age.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402

logger = get_logger("cleanup_uploads")

SECONDS_PER_DAY = 24 * 60 * 60


def job_age_seconds(sidecar: Path) -> float:
    """Age in seconds, preferring the job's recorded ``created_at``."""
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        created = data.get("created_at")
        if created:
            from datetime import datetime, timezone

            stamp = datetime.fromisoformat(created)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return time.time() - stamp.timestamp()
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return time.time() - sidecar.stat().st_mtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up old video uploads.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Remove every upload regardless of age.",
    )
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    base = settings.upload_dir_absolute
    max_age = settings.keep_uploads_days * SECONDS_PER_DAY

    removed = 0
    for entry in sorted(base.iterdir()):
        if not entry.is_file() or entry.name == ".gitkeep":
            continue

        try:
            resolved = entry.resolve()
        except OSError:
            continue
        if resolved.parent != base:
            logger.warning("Skipping unexpected path: %s", entry.name)
            continue

        if entry.suffix == ".json":
            age = job_age_seconds(entry)
        else:
            age = time.time() - entry.stat().st_mtime

        if not args.all and age < max_age:
            continue

        if args.dry_run:
            logger.info("Would remove %s (age %.1f days)", entry.name, age / SECONDS_PER_DAY)
        else:
            entry.unlink(missing_ok=True)
            logger.info("Removed %s", entry.name)
        removed += 1

    verb = "would be" if args.dry_run else "were"
    print(f"{removed} upload file(s) {verb} removed from {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())