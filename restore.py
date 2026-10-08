"""Interactively restore a validated local SQLite backup."""

import os
from pathlib import Path
import sqlite3
import tempfile

from backup import (
    DATABASE_PATH,
    LOCAL_BACKUP_DIR,
    create_local_backup,
    validate_sqlite_database,
)


def list_local_backups(backup_dir: Path = LOCAL_BACKUP_DIR) -> list[Path]:
    """Return local backups in chronological filename order."""
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []
    return sorted(
        (
            backup_path
            for backup_path in backup_dir.glob("leads_backup_*.db")
            if backup_path.is_file()
        ),
        key=lambda backup_path: backup_path.name,
    )


def restore_database(
    selected_backup: Path,
    database_path: Path = DATABASE_PATH,
    backup_dir: Path = LOCAL_BACKUP_DIR,
) -> Path | None:
    """Validate, preserve the current database, and atomically install a backup."""
    selected_backup = Path(selected_backup)
    database_path = Path(database_path)
    if selected_backup.resolve() == database_path.resolve():
        raise ValueError("The selected backup must not be the current database.")
    validate_sqlite_database(selected_backup)

    current_backup = None
    if database_path.is_file():
        current_backup = create_local_backup(database_path, backup_dir)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.restore-",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    source = None
    destination = None
    try:
        source = sqlite3.connect(
            f"{selected_backup.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        destination = sqlite3.connect(str(temporary_path))
        source.backup(destination)
        destination.close()
        destination = None
        source.close()
        source = None
        validate_sqlite_database(temporary_path)
        os.replace(temporary_path, database_path)
    except Exception:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        temporary_path.unlink(missing_ok=True)
        raise

    return current_backup


def main() -> int:
    backups = list_local_backups(LOCAL_BACKUP_DIR)
    if not backups:
        print(f"No local backups found in {LOCAL_BACKUP_DIR}.")
        return 1

    print("Available backups:")
    for index, backup_path in enumerate(backups, start=1):
        print(f"{index}. {backup_path.name}")

    try:
        selected_number = int(input("Select backup: ").strip())
    except (ValueError, EOFError):
        print("[ERROR] Please enter a valid backup number.")
        return 1

    if not 1 <= selected_number <= len(backups):
        print("[ERROR] The selected backup number is out of range.")
        return 1
    selected_backup = backups[selected_number - 1]

    try:
        validate_sqlite_database(selected_backup)
    except (OSError, sqlite3.Error) as exc:
        print(f"[ERROR] Selected backup is invalid: {exc}")
        return 1

    print()
    print("WARNING:")
    print("Restoring this backup will replace the current database.")
    try:
        confirmation = input("Type RESTORE to continue: ").strip()
    except EOFError:
        print("[ERROR] Restore cancelled.")
        return 1
    if confirmation != "RESTORE":
        print("[INFO] Restore cancelled.")
        return 0

    if DATABASE_PATH.is_file():
        print("Creating a backup of the current database first...")
    else:
        print("[WARNING] Current leads.db not found; no pre-restore backup can be created.")

    try:
        current_backup = restore_database(
            selected_backup,
            DATABASE_PATH,
            LOCAL_BACKUP_DIR,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"[ERROR] Restore failed: {exc}")
        return 1

    if current_backup is not None:
        print(f"[OK] Current database backed up to: {current_backup}")
    print(f"[OK] Database restored from: {selected_backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
