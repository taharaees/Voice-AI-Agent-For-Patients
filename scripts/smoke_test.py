import json
import os
import sys
import urllib.error
import urllib.request
from uuid import UUID


base_url = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
token = os.environ.get("API_KEY")
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"


def request(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base_url + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


status, health = request("GET", "/health")
assert status == 200 and health["data"]["status"] == "ok", health
payload = {
    "first_name": "Taylor", "last_name": "Demo-Only", "date_of_birth": "1991-06-15",
    "sex": "Other", "phone_number": "2025550186", "address_line_1": "99 Fictional Way",
    "city": "Springfield", "state": "VA", "zip_code": "22150",
}
status, created = request("POST", "/patients", payload)
if status != 201:
    print(json.dumps(created, indent=2))
    sys.exit(f"Smoke-test create failed with HTTP {status}")
patient_id = created["data"]["patient_id"]
UUID(patient_id)
status, retrieved = request("GET", f"/patients/{patient_id}")
assert status == 200 and retrieved["data"]["first_name"] == "Taylor", retrieved
status, deleted = request("DELETE", f"/patients/{patient_id}")
assert status == 200 and deleted["data"]["deleted"] is True, deleted
status, hidden = request("GET", f"/patients/{patient_id}")
assert status == 404 and hidden["error"], hidden
print("Smoke test passed: health, create, retrieve, and soft delete verified with fictional data.")
