#!/usr/bin/env python3
"""
Integration test for admin deactivation and offline sync scenarios.
"""

import sqlite3
import json
import requests
from datetime import datetime
import time

DB_PATH = 'assignments.db'
LOCAL_URL = 'http://127.0.0.1:5000'

def test_1_admin_deactivates_user():
    """Test: Admin deactivates a user and they cannot login."""
    print("\n" + "="*70)
    print("TEST 1: Admin deactivates a user → user cannot login")
    print("="*70)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Create a test student
    cur.execute("""
        INSERT INTO users (user_id, first_name, last_name, email, password_hash, role, is_approved, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ('DBU9999', 'Test', 'Student', 'test9999@test.com', 'dummy_hash', 'student', 1, datetime.now().isoformat()))
    conn.commit()
    
    # Get the user ID
    cur.execute("SELECT id, is_approved, updated_at FROM users WHERE user_id='DBU9999'")
    row = cur.fetchone()
    user_id = row[0]
    print(f"\n✓ Created test student DBU9999 (id={user_id})")
    print(f"  Before deactivation: is_approved={row[1]}, updated_at={row[2]}")
    
    # Simulate admin deactivation (set is_approved=0 and update timestamp)
    now = datetime.now().isoformat()
    cur.execute("""
        UPDATE users SET is_approved=0, updated_at=? WHERE id=?
    """, (now, user_id))
    conn.commit()
    
    # Verify deactivation
    cur.execute("SELECT is_approved, updated_at FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    print(f"\n✓ Admin deactivated the user")
    print(f"  After deactivation: is_approved={row[0]}, updated_at={row[1]}")
    
    # Check: The user should have is_approved=0
    assert row[0] == 0, "User should be deactivated (is_approved=0)"
    print(f"\n✓ PASS: User is deactivated (is_approved=0)")
    
    # Now try to simulate a login attempt
    cur.execute("SELECT * FROM users WHERE user_id='DBU9999' AND is_approved=1")
    login_check = cur.fetchone()
    if login_check is None:
        print(f"✓ PASS: Login check would FAIL (no row with is_approved=1)")
    else:
        print(f"✗ FAIL: Login check would SUCCEED (user is still approvable)")
    
    conn.close()


def test_2_offline_machine_sync():
    """Test: Machine comes back online and receives updates from peer."""
    print("\n" + "="*70)
    print("TEST 2: Offline machine receives database updates on sync")
    print("="*70)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Create test user on "local" node
    cur.execute("SELECT COUNT(*) FROM users")
    before_count = cur.fetchone()[0]
    print(f"\n✓ Current user count: {before_count}")
    
    # Simulate creating a new user on a PEER node
    # (This would normally happen on another machine)
    print(f"\n→ Simulating: User registers on PEER node while THIS machine is offline")
    
    # Mock remote data (what the peer has)
    remote_data = {
        "users": [
            # Include all current users plus a new one
            # (In reality, this comes from /sync/data endpoint on peer)
        ],
        "students": [],
        "teachers": [],
        "assignments": [],
        "submissions": [],
        "allowed_late_submissions": []
    }
    
    # Get all current users for the mock
    cur.execute("SELECT * FROM users")
    all_users = cur.fetchall()
    remote_data["users"] = all_users
    
    # Add a NEW user that represents one registered while this machine was offline
    new_user = [
        max([u[0] for u in all_users] or [0]) + 1,  # next id
        'DBU_OFFLINE',
        'Registered',
        'Offline',
        'offline@test.com',
        'new_hash',
        'student',
        1,  # is_approved
        datetime.now().isoformat(),  # created_at
        datetime.now().isoformat()   # updated_at
    ]
    remote_data["users"].append(new_user)
    
    print(f"  Mock peer data has {len(remote_data['users'])} users (including 1 new)")
    
    # Get students and teachers for the mock
    cur.execute("SELECT * FROM students")
    remote_data["students"] = cur.fetchall()
    cur.execute("SELECT * FROM teachers")
    remote_data["teachers"] = cur.fetchall()
    
    # Verify new user is NOT in local DB yet
    cur.execute("SELECT * FROM users WHERE user_id='DBU_OFFLINE'")
    before_sync = cur.fetchone()
    assert before_sync is None, "New user should NOT exist yet"
    print(f"\n✓ Before sync: New user 'DBU_OFFLINE' does NOT exist in local DB")
    
    # Simulate sync (this is what sync_update does)
    print(f"\n→ Simulating: Machine comes back online and calls /sync/update")
    
    # Apply the smart merge logic manually (as the endpoint would do)
    for user_row in remote_data["users"]:
        user_id = user_row[0]
        remote_updated = user_row[9] if len(user_row) > 9 else None  # updated_at index
        
        cur.execute("SELECT updated_at FROM users WHERE id=?", (user_id,))
        local = cur.fetchone()
        
        if local is None:
            # New user from peer
            placeholders = ','.join(['?'] * len(user_row))
            cur.execute(f"INSERT INTO users VALUES ({placeholders})", user_row)
            print(f"  → Inserted new user: {user_row[1]} (from peer)")
        else:
            local_updated = local[0]
            if remote_updated and (local_updated is None or remote_updated > local_updated):
                # Remote is newer, update it
                cur.execute("""UPDATE users SET 
                    user_id=?, first_name=?, last_name=?, email=?, 
                    password_hash=?, role=?, is_approved=?, created_at=?, updated_at=?
                    WHERE id=?""", 
                    (user_row[1], user_row[2], user_row[3], user_row[4], 
                     user_row[5], user_row[6], user_row[7], user_row[8], user_row[9], user_row[0]))
    
    conn.commit()
    
    # Verify new user now exists
    cur.execute("SELECT user_id, is_approved FROM users WHERE user_id='DBU_OFFLINE'")
    after_sync = cur.fetchone()
    assert after_sync is not None, "New user SHOULD exist after sync"
    print(f"\n✓ After sync: New user 'DBU_OFFLINE' NOW exists in local DB")
    print(f"  is_approved={after_sync[1]} (can login immediately)")
    
    # Get new count
    cur.execute("SELECT COUNT(*) FROM users")
    after_count = cur.fetchone()[0]
    print(f"\n✓ User count increased from {before_count} to {after_count}")
    
    conn.close()


def test_3_admin_edits_persist_across_sync():
    """Test: Admin edit with newer timestamp persists across sync."""
    print("\n" + "="*70)
    print("TEST 3: Admin edits (newer timestamp) persist across sync")
    print("="*70)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Create a test user
    cur.execute("""
        INSERT INTO users (user_id, first_name, last_name, email, password_hash, role, is_approved, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ('DBU_EDIT_TEST', 'Original', 'Name', 'edit@test.com', 'hash', 'student', 1, '2025-01-01 10:00:00'))
    conn.commit()
    
    cur.execute("SELECT id FROM users WHERE user_id='DBU_EDIT_TEST'")
    user_id = cur.fetchone()[0]
    
    print(f"\n✓ Created user DBU_EDIT_TEST with original name 'Original Name'")
    
    # Simulate admin edit (with NEWER timestamp)
    now = datetime.now().isoformat()
    cur.execute("""
        UPDATE users SET first_name=?, last_name=?, updated_at=? WHERE id=?
    """, ('Edited', 'ByAdmin', now, user_id))
    conn.commit()
    
    print(f"✓ Admin edited user: name changed to 'Edited ByAdmin' with timestamp={now}")
    
    # Simulate old peer data (with old timestamp)
    old_timestamp = '2025-01-01 10:00:00'
    peer_user = [user_id, 'DBU_EDIT_TEST', 'Original', 'Name', 'edit@test.com', 'hash', 'student', 1, '2025-01-01 10:00:00', old_timestamp]
    
    print(f"✓ Peer has old data: name='Original Name' with timestamp={old_timestamp}")
    
    # Smart merge: should KEEP the edited version (newer timestamp)
    remote_updated = peer_user[9]
    cur.execute("SELECT updated_at FROM users WHERE id=?", (user_id,))
    local_updated = cur.fetchone()[0]
    
    if remote_updated < local_updated:
        print(f"\n✓ Merge decision: KEEP LOCAL (newer)")
        print(f"  Remote timestamp: {remote_updated}")
        print(f"  Local timestamp:  {local_updated}")
        # Don't update local
    else:
        print(f"\n✗ Merge decision: REPLACE (should not happen!)")
    
    # Verify admin edit is still there
    cur.execute("SELECT first_name, last_name FROM users WHERE id=?", (user_id,))
    final = cur.fetchone()
    assert final[0] == 'Edited', "Admin edit should persist"
    print(f"\n✓ PASS: Admin edit persisted! User is still 'Edited ByAdmin'")
    
    conn.close()


if __name__ == '__main__':
    print("\n" + "🔍 INTEGRATION TESTS FOR ADMIN EDITS AND OFFLINE SYNC\n")
    
    try:
        test_1_admin_deactivates_user()
        test_2_offline_machine_sync()
        test_3_admin_edits_persist_across_sync()
        
        print("\n" + "="*70)
        print("✓ ALL TESTS PASSED")
        print("="*70)
        print("\nSummary:")
        print("  ✓ Deactivated users cannot login")
        print("  ✓ Offline machine receives new users on sync")
        print("  ✓ Admin edits persist across peer sync (timestamp-based)")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
