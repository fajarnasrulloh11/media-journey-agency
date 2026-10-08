# Media Journey

## Database Backup

Backup scripts are standalone utilities and do not change the Flask routes or
the SQLite database schema. The local Flask database is `leads.db`.

### Backup structure

```text
backups/
└── local/
    └── leads_backup_YYYY-MM-DD_HH-MM-SS.db
credentials/
└── google_credentials.json
```

The local backup is created with SQLite's backup API, so it includes a
consistent snapshot even when SQLite is using a journal. Local database files,
backups, and Drive credentials are excluded from Git.

### Install dependencies

From the project directory, install dependencies with:

```powershell
python -m pip install -r requirements.txt
```

### Configure environment

Copy `.env.example` to `.env`, then set the Google Drive folder ID:

```dotenv
GOOGLE_DRIVE_FOLDER_ID=your_google_drive_folder_id
BACKUP_RETENTION_DAYS=7
```

`GOOGLE_DRIVE_FOLDER_ID` is the ID of the Drive folder that should receive
backups. `BACKUP_RETENTION_DAYS` defaults to 7 and controls the explicit local
cleanup command; it does not automatically remove backups during backup or
restore.

### Create a local and Google Drive backup

```powershell
python backup.py
```

The script creates a timestamped backup under `backups/local/` first, then
uploads that file to Google Drive. A Drive upload failure is reported as a
warning and does not remove the local backup. If Drive is not configured,
local backup still works and the cloud upload is reported as failed.

### Set up Google Drive

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create
   a project, or select an existing project.
2. In **APIs & Services → Library**, find **Google Drive API** and enable it
   for the project.
3. In **IAM & Admin → Service Accounts**, create a service account for this
   backup utility.
4. Open the service account's **Keys** page and create a JSON key. Save the
   downloaded file as
   `credentials/google_credentials.json` in the project directory. Do not put
   its contents in source code, `.env`, terminal output, or Git.
5. Create or select a Google Drive folder for backups. Share the folder with
   the service account's email address and give it **Editor** access. Without
   sharing the folder with that service account, uploads will fail.
6. Open the folder in Google Drive. Its folder ID is the part of the URL after
   `/folders/`; copy that value into `GOOGLE_DRIVE_FOLDER_ID` in `.env`.
7. Run `python backup.py` and check for the cloud upload success message.

Keep the service account JSON key private and rotate/revoke it if it is exposed.

### Restore a backup

Stop the Flask application before restoring so it cannot write to the database
while the file is replaced. Then run:

```powershell
python restore.py
```

Choose a backup by its number and type `RESTORE` after reading the warning.
The script validates the chosen backup with SQLite before making changes, saves
the current `leads.db` to `backups/local/` first when it exists, and installs
the selected database. Existing backup files are not removed by restore.

### Clean up old local backups

Cleanup is an explicit operation; it does not delete Google Drive backups.
Set `BACKUP_RETENTION_DAYS` in `.env` (default: `7`), then run:

```powershell
python backup.py --cleanup
```

Only local files matching `leads_backup_*.db` older than the configured number
of days are removed. Review the retention value before running cleanup.

### Common errors

- **Database not found:** Run the command from the project setup where
  `leads.db` exists beside `app.py`, or restore/create that database first.
- **Google Drive credentials not found:** Add the service account JSON file at
  `credentials/google_credentials.json`.
- **Google Drive upload failed:** Check the folder ID, enable Google Drive API,
  verify the JSON key, and ensure the folder is shared with the service
  account's email address as an Editor.
- **Permission denied:** Check write permission for the project directory,
  `backups/local/`, and the shared Drive folder.
- **Invalid backup:** Do not restore the file. Choose a different backup and
  keep the current database intact.
- **Restore fails while Flask is running:** Stop Flask and any other process
  using `leads.db`, then retry. The pre-restore backup is retained if it was
  successfully created.

### Existing files accidentally tracked by Git

The ignore rules prevent future untracked `.env`, credential, SQLite database,
and backup files from being added. They do not remove files already tracked by
Git. To stop tracking a sensitive file without deleting your local copy, first
inspect `git ls-files` and then run the appropriate command, for example:

```powershell
git rm --cached -- .env
git rm --cached -- credentials/google_credentials.json
git rm --cached -- leads.db
```

Commit the resulting index change after checking it. If real credentials were
ever committed, revoke/rotate them; removing them from the latest commit does
not erase Git history.
api admin "fallback_rahasia123"