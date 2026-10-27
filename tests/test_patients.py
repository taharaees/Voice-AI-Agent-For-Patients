from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.schemas.patient import PatientCreate, PatientUpdate
from app.voice.vapi import vapi_tool_schemas


def create(client: TestClient, payload: dict):
    return client.post("/patients", json=payload)


def test_create_and_uuid_lookup(client, patient_payload):
    response = create(client, patient_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["error"] is None
    assert body["data"]["patient_id"]
    assert body["data"]["phone_number"] == "2025550142"
    assert body["data"]["created_at"].endswith("Z") or "+00:00" in body["data"]["created_at"]
    found = client.get(f"/patients/{body['data']['patient_id']}")
    assert found.status_code == 200
    assert found.json()["data"]["last_name"] == patient_payload["last_name"]


def test_filters_and_duplicate_phone_lookup(client, patient_payload):
    create(client, patient_payload)
    assert len(client.get("/patients?last_name=Fictional-Sample").json()["data"]) == 1
    assert len(client.get("/patients?date_of_birth=1988-04-12").json()["data"]) == 1
    matches = client.get("/patients?phone_number=+1%20202-555-0142").json()["data"]
    assert len(matches) == 1


def test_partial_update(client, patient_payload):
    created = create(client, patient_payload).json()["data"]
    response = client.put(f"/patients/{created['patient_id']}", json={"city": "New Town"})
    assert response.status_code == 200
    assert response.json()["data"]["city"] == "New Town"
    assert response.json()["data"]["first_name"] == "Jamie"
    assert response.json()["data"]["created_at"] == created["created_at"]
    assert response.json()["data"]["updated_at"] >= created["updated_at"]


def test_partial_update_rejects_null_required_fields(client, patient_payload):
    patient_id = create(client, patient_payload).json()["data"]["patient_id"]
    response = client.put(f"/patients/{patient_id}", json={"city": None})
    assert response.status_code == 422
    assert response.json()["error"]


def test_soft_delete_hides_from_normal_retrieval(client, patient_payload):
    patient_id = create(client, patient_payload).json()["data"]["patient_id"]
    result = client.delete(f"/patients/{patient_id}")
    assert result.status_code == 200
    assert result.json()["error"] is None
    assert client.get(f"/patients/{patient_id}").status_code == 404
    assert client.get("/patients").json()["data"] == []


def test_invalid_values_return_enveloped_422(client, patient_payload):
    invalid_cases = [
        {"date_of_birth": "2999-01-01"}, {"phone_number": "123"}, {"state": "XX"}, {"zip_code": "1234"},
    ]
    for change in invalid_cases:
        payload = patient_payload | change
        response = create(client, payload)
        assert response.status_code == 422
        assert response.json()["data"] is None
        assert response.json()["error"]["message"] == "Request validation failed"
        assert all("input" not in detail for detail in response.json()["error"]["details"])


def test_missing_required_fields(client, patient_payload):
    del patient_payload["first_name"]
    response = create(client, patient_payload)
    assert response.status_code == 422
    assert response.json()["error"] is not None


def test_missing_uuid_and_malformed_uuid(client):
    assert client.get("/patients/00000000-0000-0000-0000-000000000001").status_code == 404
    malformed = client.get("/patients/not-a-uuid")
    assert malformed.status_code == 422
    assert malformed.json()["error"] is not None


def test_duplicate_detection_is_available_by_phone(client, patient_payload):
    create(client, patient_payload)
    found = client.get("/patients", params={"phone_number": "2025550142"}).json()["data"]
    assert len(found) == 1
    assert found[0]["first_name"] == "Jamie"


def test_database_write_error_is_sanitized(client, patient_payload, caplog):
    failure = OperationalError("insert patient", {"email": "sensitive@example.com"}, Exception("private database details"))
    with patch("app.routes.patients.crud.create_patient", side_effect=failure):
        response = create(client, patient_payload)
    assert response.status_code == 500
    assert response.json()["error"] is not None
    assert "private database details" not in response.text
    assert "sensitive@example.com" not in response.text
    assert "sensitive@example.com" not in caplog.text


def test_health_envelope(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}, "error": None}


def test_vapi_create_tool_saves_only_after_explicit_confirmation(client, patient_payload):
    call = {"id": "call-1", "type": "function", "function": {"name": "create_patient_record", "arguments": patient_payload}}
    denied = client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [call]}})
    assert denied.status_code == 200
    assert denied.json()["results"][0]["error"]
    assert client.get("/patients").json()["data"] == []

    call["function"]["arguments"] = patient_payload | {"caller_confirmed": False}
    denied = client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [call]}})
    assert denied.json()["results"][0]["error"]
    assert client.get("/patients").json()["data"] == []

    confirmed_payload = patient_payload | {"caller_confirmed": True}
    call["function"]["arguments"] = confirmed_payload
    saved = client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [call]}})
    assert saved.status_code == 200
    result = saved.json()["results"][0]
    assert "error" not in result
    assert '"success": true' in result["result"]


def test_vapi_reports_database_write_failure_without_success(client, patient_payload):
    call = {"id": "call-3", "type": "function", "function": {
        "name": "create_patient_record", "arguments": patient_payload | {"caller_confirmed": True},
    }}
    with patch("app.voice.vapi.crud.create_patient", side_effect=OperationalError("insert patient", {}, Exception("db failure"))):
        response = client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [call]}})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["error"]
    assert "result" not in result
    assert client.get("/patients").json()["data"] == []


def test_validation_failures_do_not_log_demographics(client, patient_payload, caplog):
    patient_payload["email"] = "sensitive-but-fictional@example.test"
    patient_payload["caller_confirmed"] = True
    call = {"id": "call-2", "type": "function", "function": {"name": "create_patient_record", "arguments": patient_payload}}
    response = client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [call]}})
    assert response.status_code == 200
    assert response.json()["results"][0]["error"]
    assert "sensitive-but-fictional@example.test" not in caplog.text


def test_vapi_identity_verification_only_returns_record_on_match(client, patient_payload):
    patient_id = create(client, patient_payload).json()["data"]["patient_id"]
    def invoke(dob: str):
        return client.post("/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": [{
            "id": "verify-1", "type": "function", "function": {"name": "verify_patient_identity", "arguments": {
                "patient_id": patient_id, "first_name": "Jamie", "last_name": "Fictional-Sample", "date_of_birth": dob,
            }},
        }]}})
    wrong = invoke("1988-04-13").json()["results"][0]["result"]
    assert '"verified": false' in wrong
    matched = invoke("1988-04-12").json()["results"][0]["result"]
    assert '"verified": true' in matched
    assert '"email": "jamie@example.com"' in matched


def test_api_key_protects_patient_routes_but_not_health(client, patient_payload, monkeypatch):
    monkeypatch.setattr("app.main.settings.api_key", "fictional-test-key")
    assert client.get("/health").status_code == 200
    assert client.get("/patients").status_code == 401
    authorized = client.get("/patients", headers={"Authorization": "Bearer fictional-test-key"})
    assert authorized.status_code == 200


def test_vapi_tool_schemas_match_patient_models():
    tools = {item["function"]["name"]: item for item in vapi_tool_schemas()}
    assert set(tools) == {"find_patient_by_phone", "verify_patient_identity", "create_patient_record", "update_patient_record"}
    create_schema = tools["create_patient_record"]["function"]["parameters"]
    create_required = {name for name, field in PatientCreate.model_fields.items() if field.is_required()}
    assert set(create_schema["properties"]) >= set(PatientCreate.model_fields) | {"caller_confirmed"}
    assert set(create_schema["required"]) == create_required | {"caller_confirmed"}
    update_schema = tools["update_patient_record"]["function"]["parameters"]
    assert set(update_schema["properties"]) >= set(PatientUpdate.model_fields) | {"patient_id", "caller_confirmed"}
    assert update_schema["required"] == ["patient_id", "caller_confirmed"]
