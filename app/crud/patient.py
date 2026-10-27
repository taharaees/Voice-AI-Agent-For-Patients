from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.patient import Patient, utc_now
from app.schemas.patient import PatientCreate, PatientUpdate


def list_patients(db: Session, *, last_name: str | None = None, date_of_birth: date | None = None, phone_number: str | None = None) -> list[Patient]:
    query = select(Patient).where(Patient.deleted_at.is_(None)).order_by(Patient.created_at.desc())
    if last_name:
        query = query.where(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth:
        query = query.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        query = query.where(Patient.phone_number == phone_number)
    return list(db.scalars(query))


def get_patient(db: Session, patient_id: UUID) -> Patient | None:
    return db.scalar(select(Patient).where(Patient.patient_id == patient_id, Patient.deleted_at.is_(None)))


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    return db.scalar(select(Patient).where(Patient.phone_number == phone_number, Patient.deleted_at.is_(None)))


def create_patient(db: Session, payload: PatientCreate) -> Patient:
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient: Patient, payload: PatientUpdate) -> Patient:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, key, value)
    patient.updated_at = utc_now()
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient: Patient) -> None:
    patient.deleted_at = utc_now()
    patient.updated_at = patient.deleted_at
    db.commit()
