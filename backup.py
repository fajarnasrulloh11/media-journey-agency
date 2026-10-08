"""Create local SQLite backups and optionally upload them to Google Drive."""

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import sys
import time

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "leads.db"
LOCAL_BACKUP_DIR = BASE_DIR / "backups" / "local"
CREDENTIALS_PATH = BASE_DIR / "credentials" / "google_credentials.json"

load_dotenv(BASE_DIR / ".env")


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)


def validate_sqlite_database(database_path: Path) -> None:
    """Raise an error unless the file passes SQLite's integrity check."""
    connection = _connect_read_only(database_path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            detail = result[0] if result else "no integrity-check result"
            raise sqlite3.DatabaseError(f"SQLite integrity check failed: {detail}")
    finally:
        connection.close()


def create_local_backup(
    database_path: Path = DATABASE_PATH,
    backup_dir: Path = LOCAL_BACKUP_DIR,
) -> Path:
    """Create and validate a timestamped backup using SQLite's backup API."""
    database_path = Path(database_path)
    backup_dir = Path(backup_dir)
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    while True:
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = backup_dir / f"leads_backup_{timestamp}.db"
        try:
            backup_path.touch(exist_ok=False)
            break
        except FileExistsError:
            time.sleep(max(0.01, 1 - now.microsecond / 1_000_000))

    source = None
    destination = None
    try:
        source = _connect_read_only(database_path)
        destination = sqlite3.connect(str(backup_path))
        source.backup(destination)
        destination.close()
        destination = None
        source.close()
        source = None
        validate_sqlite_database(backup_path)
        return backup_path
    except Exception:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        backup_path.unlink(missing_ok=True)
        raise


def cleanup_local_backups(
    retention_days: int,
    backup_dir: Path = LOCAL_BACKUP_DIR,
) -> list[Path]:
    """Delete timestamped local backups older than the requested retention."""
    if retention_days < 1:
        raise ValueError("BACKUP_RETENTION_DAYS must be a positive integer.")

    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []

    cutoff = time.time() - timedelta(days=retention_days).total_seconds()
    removed = []
    for backup_path in backup_dir.glob("leads_backup_*.db"):
        if backup_path.is_file() and backup_path.stat().st_mtime < cutoff:
            backup_path.unlink()
            removed.append(backup_path)
    return removed


def _retention_days_from_environment() -> int:
    raw_value = os.getenv("BACKUP_RETENTION_DAYS", "7")
    try:
        retention_days = int(raw_value)
    except ValueError as exc:
        raise ValueError("BACKUP_RETENTION_DAYS must be a positive integer.") from exc
    if retention_days < 1:
        raise ValueError("BACKUP_RETENTION_DAYS must be a positive integer.")
    return retention_days


def upload_to_google_drive(
    backup_path: Path,
    folder_id: str,
    credentials_path: Path = CREDENTIALS_PATH,
) -> str:
    """Upload a backup with Google Drive API using a service account."""
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID is not configured.")
    if not credentials_path.is_file():
        raise FileNotFoundError(
            f"Google Drive credentials not found: {credentials_path}"
        )

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    media = MediaFileUpload(str(backup_path), mimetype="application/x-sqlite3")
    result = (
        service.files()
        .create(
            body={"name": backup_path.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return result["id"]


def _run_cleanup() -> int:
    try:
        retention_days = _retention_days_from_environment()
        removed = cleanup_local_backups(retention_days)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] Local backup cleanup failed: {exc}")
        return 1

    print(f"[OK] Removed {len(removed)} local backup(s) older than {retention_days} days.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Media Journey database backup")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="delete local backups older than BACKUP_RETENTION_DAYS (default: 7)",
    )
    args = parser.parse_args(argv)
    if args.cleanup:
        return _run_cleanup()

    print("# ==================================================")
    print("MEDIA JOURNEY DATABASE BACKUP")
    print("[1/2] Checking database...")
    if not DATABASE_PATH.is_file():
        print(f"[ERROR] Database not found: {DATABASE_PATH}")
        return 1
    print("[OK] leads.db found")

    print()
    print("[2/2] Creating local backup...")
    try:
        backup_path = create_local_backup()
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"[ERROR] Local backup failed: {exc}")
        return 1
    print(f"[OK] Local backup created: {backup_path.relative_to(BASE_DIR)}")

    print()
    print("Uploading to Google Drive...")
    try:
        upload_to_google_drive(
            backup_path,
            os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip(),
        )
    except Exception as exc:
        print(f"[WARNING] Cloud backup failed: {type(exc).__name__}: {exc}")
        print("[OK] Local backup is still available.")
    else:
        print("[OK] Cloud backup uploaded")

    print()
    print("# ==================================================")
    print("Backup completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
