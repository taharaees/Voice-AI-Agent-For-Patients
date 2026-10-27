# Voice AI Patient Registration Challenge Requirements

Source: `Voice AI Agent Coding Challenge ..pdf` (8 pages), extracted in full.

## Traceability checklist

Statuses describe local code coverage, not external-provider verification. The suite ran locally; PostgreSQL and Vapi remain unconfigured. Each requirement below is marked Implemented, Incomplete, or Unverified.

### Voice and telephony
- [Incomplete] Provision a real, dialable U.S. phone number through a voice/telephony provider (manual Vapi provisioning required).
- [Unverified] Natural conversational intake rather than a rigid IVR flow.
- [Unverified] LLM understands varied phrasing, asks clarifying questions, and handles corrections and out-of-order responses.
- [Unverified] Collect all required patient demographics; offer optional fields without requiring them.
- [Unverified] Reprompt specifically for invalid values (examples: 3-digit phone number, future DOB).
- [Unverified] Read back all collected information and get explicit confirmation or corrections before saving.
- [Incomplete] Writes require a model-supplied `caller_confirmed=true` and the prompt requires explicit consent, but the server cannot independently verify the caller utterance; successful/failed tool responses are implemented and covered in tests.
- [Unverified] On success, give a brief confirmation and end the call gracefully (Vapi Hang Up tool must be attached in dashboard).
- [Unverified] Handle dropped calls and caller requests to start over gracefully.
- [Incomplete] Phone lookup and name/DOB verification tools exist, but live flow is unverified and update authorization is not bound to verified lookup; full existing-record review/update still needs work.
- [Incomplete] Full payload logging is intentionally omitted for privacy; current logs keep operation and patient ID only. Add a redacted event with opaque call/request ID, outcome, duration, and field-presence flags, without values.

### Bonus challenges
- [Incomplete] Appointment scheduling is not implemented.
- [Incomplete] Spanish or other multilingual conversation switching is not implemented.
- [Incomplete] Call transcript/summary persistence is not implemented.
- [Incomplete] Patient dashboard is not implemented.
- [Implemented] Automated API tests are present and pass locally; live voice-call simulations remain unverified.

### Patient model and validation
- [Implemented] `patient_id`: unique auto-generated UUID.
- [Implemented] `first_name`: required, 1-50 chars, alphabetic with hyphens/apostrophes allowed.
- [Implemented] `last_name`: required, 1-50 chars, alphabetic with hyphens/apostrophes allowed.
- [Implemented] `date_of_birth`: required valid date, not in the future; voice format MM/DD/YYYY.
- [Implemented] `sex`: required enum: Male, Female, Other, Decline to Answer.
- [Implemented] `phone_number`: required valid U.S. 10-digit number, normalized before persistence.
- [Implemented] `email`: optional valid email.
- [Implemented] `address_line_1`: required street address.
- [Implemented] `address_line_2`: optional apartment/suite/unit.
- [Implemented] `city`: required, 1-100 characters.
- [Implemented] `state`: required valid two-letter U.S. state abbreviation.
- [Implemented] `zip_code`: required five-digit or ZIP+4 format.
- [Implemented] `insurance_provider`: optional insurance company name.
- [Implemented] `insurance_member_id`: optional alphanumeric member/subscriber ID.
- [Implemented] `preferred_language`: optional; default English.
- [Implemented] `emergency_contact_name`: optional full name.
- [Implemented] `emergency_contact_phone`: optional valid U.S. 10-digit number.
- [Implemented] `created_at`: automatic UTC timestamp on creation.
- [Implemented] `updated_at`: automatic UTC timestamp on modification.
- [Implemented] `deleted_at`: nullable UTC timestamp for soft deletion.
- [Implemented] Enforce suitable schema constraints and reject invalid data server-side.

### Database
- [Implemented] Local SQLite persistence and SQLAlchemy relational schema.
- [Unverified] PostgreSQL/Supabase URL support is coded, but no PostgreSQL service or restart-persistence deployment has been tested.
- [Implemented] Appropriate column types and constraints for the complete demographic model.
- [Implemented] Do not use real patient data; tests and smoke script use fictional values.

### REST service
- [Implemented] `GET /health` health response.
- [Implemented] `GET /patients` list patients; optional filters `last_name`, `date_of_birth`, `phone_number`.
- [Implemented] `GET /patients/{id}` retrieve by UUID.
- [Implemented] `POST /patients` create and return the generated UUID.
- [Implemented] `PUT /patients/{id}` update an existing record; partial update allowed.
- [Implemented] `DELETE /patients/{id}` soft-delete by setting `deleted_at`, never hard-delete.
- [Implemented] Exclude deleted patients from ordinary retrieval and filtering.
- [Implemented] Use consistent JSON envelope `{ "data": ..., "error": ... }`.
- [Implemented] Return appropriate HTTP status codes, including 200, 201, 400, 404, 422, and 500 as applicable.
- [Implemented] Sanitize and validate all input server-side; don't rely on the voice agent.
- [Implemented] Database errors must not leak sensitive internals.

### Quality, delivery, and submission
- [Implemented] Clean separation of telephony/LLM, API, service/CRUD, model, schema, and DB configuration.
- [Implemented] README documents setup, architecture, stack decisions, env vars, trade-offs, and limitations.
- [Implemented] Automated tests cover API behavior and edge cases (17 tests passed locally).
- [Implemented] Prepare deployment-compatible config, requirements, `.env.example`, `.gitignore`, and smoke test.
- [Implemented] Do not hardcode or commit secrets.
- [Incomplete] Deployment is live/callable for review, with repository URL, phone number, API base URL, and any testing notes submitted.
- [Implemented] Manual steps (accounts, credentials, billing, number provisioning, deploy) are documented for the owner; execution is still required.
- [Incomplete] Submission details (repository URL, live phone number, API base URL, reviewer credentials/notes) are not yet available because nothing is deployed.


## Minimal architecture proposal

FastAPI exposes a versionless REST API. Pydantic schemas validate and normalize input; SQLAlchemy models and CRUD functions persist data in PostgreSQL (Supabase), with SQLite supported for local development/tests. A Vapi assistant handles speech, turn-taking, and confirmation, then invokes a narrowly scoped backend tool only after the caller confirms. The backend owns validation, duplicate lookup, persistence, and response envelopes. Render runs the API; Vapi hosts the assistant and phone integration.

```text
Caller <-> Vapi assistant + tool call -> FastAPI -> SQLAlchemy -> Supabase/PostgreSQL
                                                `-> GET /health and patient REST API
```

## Proposed project structure

```text
app/
  main.py                 # FastAPI app and error envelope handlers
  core/config.py          # environment settings
  db/session.py           # engine and session dependency
  models/patient.py       # SQLAlchemy patient model
  schemas/patient.py      # Pydantic validation and response schemas
  crud/patient.py         # persistence/query operations
  routes/patients.py      # REST endpoints
  voice/vapi.py           # assistant prompt/tool configuration helpers
tests/
  conftest.py
  test_patients.py
scripts/smoke_test.py
```

## Owner actions required for a live phone demo

- [Incomplete] Create/configure Supabase (or provide a PostgreSQL connection string) and secure its credentials.
- [Incomplete] Create a Render account/service and set environment variables; approve billing if required.
- [Incomplete] Create a Vapi account, provide/configure a model and voice provider, and approve usage billing.
- [Incomplete] Provision or import a U.S. phone number in Vapi and attach the assistant; this requires account access and may require billing/provider verification.
- [Incomplete] Set the deployed API base URL in the Vapi tool configuration, then place a fictional-data smoke-test call.
- [Incomplete] Publish the repository and provide repository URL, phone number, API URL, and reviewer notes. These external actions require account ownership and are not claimed complete by local implementation.
