import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud import patient as crud
from app.db.session import get_db
from app.schemas.patient import DeleteResult, PatientCreate, PatientRead, PatientUpdate, ResponseEnvelope, normalize_us_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["patients"])


def _save_error(exc: SQLAlchemyError) -> HTTPException:
    logger.error("Patient write failed (exception_type=%s)", type(exc).__name__)
    if isinstance(exc, IntegrityError):
        return HTTPException(status_code=400, detail="Patient data conflicts with a database constraint")
    return HTTPException(status_code=500, detail="The patient record could not be saved")


@router.get("", response_model=ResponseEnvelope[list[PatientRead]])
def list_patients(
    last_name: str | None = Query(default=None, min_length=1, max_length=50),
    date_of_birth: date | None = None,
    phone_number: str | None = None,
    db: Session = Depends(get_db),
):
    if phone_number is not None:
        try:
            phone_number = normalize_us_phone(phone_number)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = crud.list_patients(db, last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number)
    return {"data": [PatientRead.model_validate(row) for row in rows], "error": None}


@router.get("/{patient_id}", response_model=ResponseEnvelope[PatientRead])
def get_patient(patient_id: UUID, db: Session = Depends(get_db)):
    row = crud.get_patient(db, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"data": PatientRead.model_validate(row), "error": None}


@router.post("", response_model=ResponseEnvelope[PatientRead], status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    logger.info("Creating patient registration record")
    try:
        row = crud.create_patient(db, payload)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _save_error(exc) from exc
    return {"data": PatientRead.model_validate(row), "error": None}


@router.put("/{patient_id}", response_model=ResponseEnvelope[PatientRead])
def update_patient(patient_id: UUID, payload: PatientUpdate, db: Session = Depends(get_db)):
    row = crud.get_patient(db, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        row = crud.update_patient(db, row, payload)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _save_error(exc) from exc
    return {"data": PatientRead.model_validate(row), "error": None}


@router.delete("/{patient_id}", response_model=ResponseEnvelope[DeleteResult])
def delete_patient(patient_id: UUID, db: Session = Depends(get_db)):
    row = crud.get_patient(db, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        crud.soft_delete_patient(db, row)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _save_error(exc) from exc
    return {"data": {"patient_id": patient_id, "deleted": True}, "error": None}
