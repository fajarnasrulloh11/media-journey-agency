import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from backup import cleanup_local_backups, create_local_backup, validate_sqlite_database
import restore
from restore import restore_database


def create_database(path: Path, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def read_value(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT value FROM records").fetchone()[0]
    finally:
        connection.close()


class DatabaseBackupTests(unittest.TestCase):
    def test_local_backup_is_a_valid_sqlite_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "leads.db"
            backup_dir = root / "backups" / "local"
            create_database(database, "before")

            backup_path = create_local_backup(database, backup_dir)

            self.assertRegex(
                backup_path.name,
                r"^leads_backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.db$",
            )
            validate_sqlite_database(backup_path)
            self.assertEqual(read_value(backup_path), "before")

    def test_restore_preserves_current_database_and_installs_selected_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "leads.db"
            backup_dir = root / "backups" / "local"
            create_database(database, "current")
            selected_backup = create_local_backup(database, backup_dir)

            connection = sqlite3.connect(database)
            connection.execute("UPDATE records SET value = 'changed'")
            connection.commit()
            connection.close()

            current_backup = restore_database(selected_backup, database, backup_dir)

            self.assertIsNotNone(current_backup)
            self.assertEqual(read_value(database), "current")
            self.assertEqual(read_value(current_backup), "changed")
            self.assertTrue(selected_backup.exists())

    def test_invalid_backup_does_not_modify_current_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "leads.db"
            backup_dir = root / "backups" / "local"
            backup_dir.mkdir(parents=True)
            create_database(database, "unchanged")
            invalid_backup = backup_dir / "leads_backup_invalid.db"
            invalid_backup.write_text("not a database", encoding="utf-8")

            with self.assertRaises(sqlite3.DatabaseError):
                restore_database(invalid_backup, database, backup_dir)

            self.assertEqual(read_value(database), "unchanged")

    def test_restore_cli_restores_selected_backup_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "leads.db"
            backup_dir = root / "backups" / "local"
            create_database(database, "before")
            selected_backup = create_local_backup(database, backup_dir)
            connection = sqlite3.connect(database)
            connection.execute("UPDATE records SET value = 'current'")
            connection.commit()
            connection.close()

            with (
                patch.object(restore, "DATABASE_PATH", database),
                patch.object(restore, "LOCAL_BACKUP_DIR", backup_dir),
                patch("builtins.input", side_effect=["1", "RESTORE"]),
            ):
                self.assertEqual(restore.main(), 0)

            self.assertEqual(read_value(database), "before")
            self.assertTrue(selected_backup.exists())
            self.assertEqual(len(list(backup_dir.glob("leads_backup_*.db"))), 2)

    def test_retention_cleanup_only_removes_expired_backup_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backup_dir = Path(directory)
            expired = backup_dir / "leads_backup_expired.db"
            recent = backup_dir / "leads_backup_recent.db"
            unrelated = backup_dir / "other.db"
            for path in (expired, recent, unrelated):
                path.touch()
            old_time = (datetime.now() - timedelta(days=8)).timestamp()
            os.utime(expired, (old_time, old_time))

            removed = cleanup_local_backups(7, backup_dir)

            self.assertEqual(removed, [expired])
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
