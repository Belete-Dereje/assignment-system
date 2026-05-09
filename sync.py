import requests
import time
import sys

# The other machine's Zerotier IP and port
OTHER = sys.argv[1] if len(sys.argv) > 1 else "10.49.210.216:5000"
LOCAL = "http://127.0.0.1:5000"

print(f"Syncing with http://{OTHER} every 60 seconds...")

while True:
    try:
        # Get data from remote
        remote = requests.get(f"http://{OTHER}/sync/data", timeout=10)
        if remote.status_code == 200:
            # Push data to local
            local = requests.post(f"{LOCAL}/sync/update", json=remote.json(), timeout=10)
            if local.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] ✅ Synced")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] ❌ Local update failed")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Remote unreachable (status {remote.status_code})")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ {str(e)[:50]}")
    
    time.sleep(60)
