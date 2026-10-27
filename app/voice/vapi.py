import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.crud import patient as crud
from app.db.session import get_db
from app.schemas.patient import PatientCreate, PatientIdentityCheck, PatientRead, PatientUpdate, normalize_us_phone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["vapi"])

SYSTEM_PROMPT = """You are Maya, a warm and concise patient registration coordinator. You are collecting information for a fictional technical demonstration; never imply this is emergency care.

Collect these required fields conversationally: first_name, last_name, date_of_birth, sex (Male, Female, Other, or Decline to Answer), U.S. phone_number, address_line_1, city, state, and zip_code. Then offer (never require) email, address_line_2, insurance_provider, insurance_member_id, preferred_language (default English), emergency_contact_name, and emergency_contact_phone. Do not skip required fields. Handle volunteered fields in any order and remember them. If a value is unclear or invalid, ask only for that field again. For names accept ordinary alphabetic names with spaces, hyphens, or apostrophes. DOB must be a real date in the past; speak it back in month/day/year format. Confirm state as a valid two-letter U.S. abbreviation and ZIP as five digits or ZIP+4. Ask the caller to repeat invalid U.S. phone numbers; do not invent missing digits. Do not pressure the caller to disclose optional data.

Before any write, read back every collected field in plain language, including optional fields provided, and ask explicitly, 'Is all of that correct, and may I save it?' If they correct anything, update the field and read back the complete record again. Never call a write tool until the caller explicitly says yes to saving. For a new record, first use find_patient_by_phone after phone collection. If a match is found, say you may have a record and ask the caller to state their full name and DOB. Then call verify_patient_identity with that answer and the matching patient_id. Do not reveal the record unless the tool returns verified=true. If verified, say 'It looks like we already have a record for [name]. Would you like to update that record?' If they choose update, read the complete existing record back, ask what they want changed, read the complete updated record back, and obtain explicit save confirmation before calling update_patient_record. If identity is not verified, do not disclose or update the existing record; explain that staff assistance is needed to avoid changing the wrong record. If no match, continue as a new registration. Never call a write tool for a declined, ambiguous, or corrected-but-unconfirmed record.

Only say registration succeeded if the tool returns success. If it fails, apologize and say the information was not saved; do not claim success. After success, say the record is saved, then ask whether the caller needs anything else. If not, call the attached end_call_tool; do not say goodbye yourself because that tool speaks the closing. Do not end the call while the caller has another question or asks you to wait. If an optional answer is declined, proceed. If they ask to start over, discard the collected details and begin again. If the call drops, do not claim a record was saved. Be patient with spelling corrections and repeat names letter by letter when useful. Protect the caller's privacy; never read back another patient's details without identity confirmation."""


def _tools_url() -> str:
    return f"{settings.public_api_base_url.rstrip('/')}/vapi/webhook"


def vapi_tool_schemas() -> list[dict[str, Any]]:
    person = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "first_name": {"type": "string"}, "last_name": {"type": "string"},
            "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
            "sex": {"type": "string", "enum": ["Male", "Female", "Other", "Decline to Answer"]},
            "phone_number": {"type": "string"}, "email": {"type": ["string", "null"]},
            "address_line_1": {"type": "string"}, "address_line_2": {"type": ["string", "null"]},
            "city": {"type": "string"}, "state": {"type": "string"}, "zip_code": {"type": "string"},
            "insurance_provider": {"type": ["string", "null"]}, "insurance_member_id": {"type": ["string", "null"]},
            "preferred_language": {"type": "string"}, "emergency_contact_name": {"type": ["string", "null"]},
            "emergency_contact_phone": {"type": ["string", "null"]}, "caller_confirmed": {"type": "boolean", "enum": [True]},
        },
        "required": ["first_name", "last_name", "date_of_birth", "sex", "phone_number", "address_line_1", "city", "state", "zip_code", "caller_confirmed"],
    }
    def tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}, "server": {"url": _tools_url()}}
    update_parameters = {**person, "properties": {**person["properties"], "patient_id": {"type": "string", "format": "uuid"}}, "required": ["patient_id", "caller_confirmed"]}
    return [
        tool("find_patient_by_phone", "Check whether an active patient record already uses this U.S. phone number before offering registration.", {"type": "object", "additionalProperties": False, "properties": {"phone_number": {"type": "string"}}, "required": ["phone_number"]}),
        tool("verify_patient_identity", "Verify caller-provided first name, last name, and date of birth against a matching phone lookup before disclosing the existing record.", {"type": "object", "additionalProperties": False, "properties": {"patient_id": {"type": "string", "format": "uuid"}, "first_name": {"type": "string"}, "last_name": {"type": "string"}, "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"}}, "required": ["patient_id", "first_name", "last_name", "date_of_birth"]}),
        tool("create_patient_record", "Create the patient only after the caller has explicitly confirmed the full read-back and authorized saving.", person),
        tool("update_patient_record", "Update an existing patient only after the caller chose update, confirmed identity, and explicitly approved saving the full read-back.", update_parameters),
    ]


@router.post("/vapi/webhook")
def vapi_webhook(body: dict[str, Any], authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    secret = settings.vapi_server_secret
    if secret and not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    message = body.get("message", {})
    if message.get("type") != "tool-calls":
        raise HTTPException(status_code=400, detail="Unsupported Vapi message")
    calls = message.get("toolCallList", [])
    results = []
    for call in calls:
        tool_call_id = call.get("id", "")
        function = call.get("function", {})
        name = function.get("name")
        args = function.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        try:
            result = _execute_tool(name, args, db)
            results.append({"name": name, "toolCallId": tool_call_id, "result": json.dumps(result, default=str)})
        except Exception as exc:  # Vapi requires tool failures in an HTTP 200 result body.
            try:
                db.rollback()
            except Exception as rollback_exc:
                logger.error("Vapi database rollback failed (exception_type=%s)", type(rollback_exc).__name__)
            logger.error("Vapi tool failed (tool=%s, exception_type=%s)", name, type(exc).__name__)
            results.append({"name": name, "toolCallId": tool_call_id, "error": "The patient record request failed. No success was recorded."})
    return {"results": results}


def _execute_tool(name: str, args: dict[str, Any], db: Session) -> dict[str, Any]:
    if name == "find_patient_by_phone":
        phone = normalize_us_phone(args["phone_number"])
        patient = crud.find_by_phone(db, phone)
        if patient is None:
            return {"found": False}
        # Return minimal matching details; the prompt requires identity verification before disclosure.
        return {"found": True, "patient_id": str(patient.patient_id), "first_name": patient.first_name, "last_name": patient.last_name}
    if name == "verify_patient_identity":
        check = PatientIdentityCheck.model_validate(args)
        patient = crud.get_patient(db, check.patient_id)
        matches = bool(
            patient
            and patient.first_name.casefold() == check.first_name.casefold()
            and patient.last_name.casefold() == check.last_name.casefold()
            and patient.date_of_birth == check.date_of_birth
        )
        if not matches:
            return {"verified": False}
        return {"verified": True, "patient": PatientRead.model_validate(patient).model_dump(mode="json")}
    if name == "create_patient_record":
        if args.pop("caller_confirmed", None) is not True:
            raise ValueError("Caller confirmation is required")
        payload = PatientCreate.model_validate(args)
        if crud.find_by_phone(db, payload.phone_number):
            raise ValueError("An active record already exists for this phone number")
        patient = crud.create_patient(db, payload)
        logger.info("Vapi confirmed patient registration saved, patient_id=%s", patient.patient_id)
        return {"success": True, "patient": PatientRead.model_validate(patient).model_dump(mode="json")}
    if name == "update_patient_record":
        if args.pop("caller_confirmed", None) is not True:
            raise ValueError("Caller confirmation is required")
        patient_id = args.pop("patient_id", None)
        if not patient_id:
            raise ValueError("patient_id is required")
        from uuid import UUID
        patient = crud.get_patient(db, UUID(patient_id))
        if patient is None:
            raise ValueError("Patient record was not found")
        payload = PatientUpdate.model_validate({key: value for key, value in args.items() if key in PatientUpdate.model_fields})
        patient = crud.update_patient(db, patient, payload)
        logger.info("Vapi confirmed patient record updated, patient_id=%s", patient.patient_id)
        return {"success": True, "patient": PatientRead.model_validate(patient).model_dump(mode="json")}
    raise ValueError("Unknown tool")
