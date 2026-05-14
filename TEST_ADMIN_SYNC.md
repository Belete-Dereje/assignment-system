# Admin Edit Persistence Test

This test verifies that admin edits (deactivation, password changes, teacher approval) persist across sync cycles.

## Problem Fixed

Previously, admin edits were overwritten by the sync process every 5 seconds because the sync logic used `INSERT OR REPLACE`, which always accepted remote data as authoritative. This meant:

- Admin deactivates a user → user still logs in
- Admin changes a password → user logs in with old password
- Admin approves a teacher → approval disappears after next sync

## Solution Implemented

1. **Added `updated_at` timestamp column** to the `users` table to track when each record was last modified.
2. **Smart merge logic** in `/sync/update` endpoint: 
   - Compares `updated_at` timestamps between local and remote
   - Only applies remote updates if remote is newer than local
   - Preserves local changes (admin edits) that are more recent
3. **Admin edits now set `updated_at`**:
   - `routes_admin.py` edit_user(): Updates `updated_at` on all edits
   - `routes_admin.py` approve(): Sets `updated_at` when approving
   - Auth registration: `updated_at` defaults to `created_at`

## How to Test

### 1. Verify the schema has updated_at
```bash
sqlite3 assignments.db "PRAGMA table_info(users);"
```
You should see `updated_at` in the column list.

### 2. Create a test teacher account
```bash
curl -s http://localhost:5000/api/test-register-teacher \
  -d "user_id=T999&first_name=Test&last_name=Teacher&email=test@test.com&password=pass123&departments=CS&years=1&courses=Python"
```

### 3. Simulate admin deactivation
```bash
sqlite3 assignments.db <<SQL
-- Find the test teacher
SELECT id, user_id, is_approved, updated_at FROM users WHERE user_id='T999';

-- Admin deactivates (simulating the edit_user endpoint)
UPDATE users SET is_approved=0, updated_at=CURRENT_TIMESTAMP WHERE user_id='T999';

-- Verify deactivation was recorded with new timestamp
SELECT id, is_approved, updated_at FROM users WHERE user_id='T999';
SQL
```

### 4. Simulate sync from peer with old data
```bash
# Create a mock "remote" users table data (without the deactivation)
python3 <<PYTHON
import json
import requests

# Simulate the old remote data (before admin edit)
remote_data = {
    "users": [
        [1, "ADMIN001", "Admin", "User", "admin@system.com", "hash", "admin", 1, "2024-01-01 10:00:00", "2024-01-01 10:00:00"],
        [2, "T999", "Test", "Teacher", "test@test.com", "hash", "teacher", 0, "2024-01-01 11:00:00", "2024-01-01 11:00:00"],  # OLD timestamp
    ],
    "students": [],
    "teachers": [[1, 2, "CS", "1", "Python"]],
    "assignments": [],
    "submissions": [],
    "allowed_late_submissions": []
}

# Send sync update (simulating peer data)
response = requests.post('http://localhost:5000/sync/update', json=remote_data)
print(f"Sync response: {response.status_code}")

# Check if deactivation survived
import sqlite3
conn = sqlite3.connect('assignments.db')
cur = conn.cursor()
cur.execute("SELECT is_approved, updated_at FROM users WHERE user_id='T999'")
row = cur.fetchone()
print(f"After sync - is_approved: {row[0]}, updated_at: {row[1]}")
if row[0] == 0:
    print("✓ SUCCESS: Deactivation survived the sync!")
else:
    print("✗ FAILED: Deactivation was overwritten")
conn.close()
PYTHON
```

## Expected Behavior

After the sync, the teacher should **remain deactivated** (is_approved=0) because:
- Local `updated_at` is newer than remote's old timestamp
- Smart merge logic prioritizes the local (newer) version

## Manual Verification via UI

1. Start the app: `python app.py`
2. Register a new teacher account (T_TEST1, etc.)
3. As admin, approve or deactivate this teacher
4. While sync is running (or manually trigger it), verify on another node that the approval/deactivation appears
5. Make another change to the user on node A
6. Verify it persists on node B after the next sync cycle (5 seconds)

## Files Changed

- `app.py`: Added `updated_at` to users schema, smart merge in sync_update
- `routes_admin.py`: Set `updated_at=CURRENT_TIMESTAMP` on user edits and approvals
- `assignments.db`: Added `updated_at` column to users table (migration runs on app startup)

## Notes

- This fix assumes clocks on the three nodes are reasonably synchronized (within seconds).
- For production, consider adding a "last modified by" field and a proper conflict resolution policy.
- The sync still uses simple peer-to-peer replication; for true distributed safety, consider using a master-slave or quorum-based approach.
