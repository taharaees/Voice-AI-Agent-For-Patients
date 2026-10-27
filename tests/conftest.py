import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import Patient  # noqa: F401


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    test_client = TestClient(app, raise_server_exceptions=False)
    # The fixture created its own schema above; avoid running the production
    # lifespan hook, which creates tables on the configured local/Postgres DB.
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def patient_payload():
    return {
        "first_name": "Jamie", "last_name": "Fictional-Sample", "date_of_birth": "1988-04-12",
        "sex": "Decline to Answer", "phone_number": "+1 (202) 555-0142", "email": "jamie@example.com",
        "address_line_1": "123 Example Street", "city": "Springfield", "state": "DC", "zip_code": "20001",
    }
