import requests
import time

OTHERS = ["10.49.210.216:5000", "10.49.210.76:5000"]
LOCAL = "http://127.0.0.1:5000"
print(f"Syncing with {OTHERS} every 5 seconds...")

while True:
    for other in OTHERS:
        try:
            remote = requests.get(f"http://{other}/sync/data", timeout=10)
            if remote.status_code == 200:
                local = requests.post(f"{LOCAL}/sync/update", json=remote.json(), timeout=10)
                if local.status_code == 200:
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ {other}")
        except:
            pass
    time.sleep(5)
