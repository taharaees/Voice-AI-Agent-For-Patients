# Voice AI Patient Registration

A small FastAPI service and Vapi voice agent for registering fictional patient records. The API owns validation and persistence; the prompt instructs Vapi to call a write tool after explicit confirmation. The backend currently receives a model-supplied confirmation flag and cannot independently prove what the caller said.

> This repository is a coding-challenge demonstration. Do not enter real patient information. It is not a clinical system and is not configured for HIPAA-regulated production use.

## Architecture

```text
Caller <-> Vapi (telephony, transcription, LLM, speech)
             | function tool calls over HTTPS
             v
        FastAPI /vapi/webhook -> Pydantic validation -> SQLAlchemy -> PostgreSQL/Supabase
                    `-------- REST /patients API
```

- FastAPI routes and envelope/error handling live in `app/main.py` and `app/routes/`.
- Pydantic validates fields, normalizes U.S. phone numbers to ten digits and states to uppercase, and checks DOB, email, ZIP, name, and member ID values.
- SQLAlchemy stores a UUID patient ID, demographic fields, UTC timestamps, and `deleted_at` for soft deletion.
- SQLite is the default for local runs; PostgreSQL is used in deployment. Tables are created on startup for this assessment. A migration tool should replace `create_all` before schema evolution in a long-lived service.
- Vapi's synchronous Function tool protocol is implemented in `app/voice/vapi.py`; errors return tool-level errors using HTTP 200. Writes require `caller_confirmed=true` and create rechecks for an existing phone, but that flag is model-supplied, not independent evidence of caller consent.
- Existing-phone lookup and name/DOB verification are implemented; binding a later update to that verified lookup and presenting the complete existing record for review remain incomplete.
- API access can be protected with `API_KEY`; Vapi webhook calls can be protected with `VAPI_SERVER_SECRET`.

## Local setup

Requires Python 3.14 for deployment parity (Vercel supports Python 3.12, 3.13, and 3.14).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --no-access-log
```

The local SQLite database is `patients.db` in the working directory. Visit `http://localhost:8000/docs` for the interactive API docs and `http://localhost:8000/health` for the health check.

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `APP_ENV` | No | `development` locally or `production` on Vercel/Render. Production refuses the local SQLite default. |
| `DATABASE_URL` | No locally; required in production | SQLAlchemy URL. Local default is `sqlite:///./patients.db`. Set the Supabase PostgreSQL connection string for deployment. `postgres://` and `postgresql://` URLs are normalized to the psycopg 3 driver. Use an appropriate Supabase PostgreSQL connection URL and any required SSL parameters. |
| `API_KEY` | Recommended in deployment | If set, protect every `/patients` request with `Authorization: Bearer <API_KEY>`. The health endpoint remains public. |
| `VAPI_SERVER_SECRET` | Recommended for Vapi | Shared webhook token. Configure a Vapi Bearer Token credential with this value and attach it to the Function tool server. |
| `PUBLIC_API_BASE_URL` | Required for Vapi tools | Public HTTPS base URL of this service, e.g. `https://your-project.vercel.app`. It is used to generate the Vapi Function tool webhook URL. |
| `VAPI_ASSISTANT_ID` | Optional | Reserved for recording the configured assistant ID in the deployment environment. |

Never commit `.env`, API keys, provider credentials, or real patient data. Use fictional records only. Successful create/update logs record the operation and patient UUID, not full demographic payloads, to avoid putting sensitive data in service logs.

## API

All responses use `{ "data": ..., "error": ... }`. Errors have `data: null` and an `error.message`; validation failures include field details. Soft-deleted records are hidden from all normal reads.

- `GET /health` — verifies API and database connectivity.
- `GET /patients?last_name=Sample&date_of_birth=1990-01-02&phone_number=2025550100` — list/filter active records. Filters can be combined.
- `GET /patients/{patient_id}` — get a record by UUID.
- `POST /patients` — create a record; returns `201`.
- `PUT /patients/{patient_id}` — partial update; supply only changed fields.
- `DELETE /patients/{patient_id}` — soft-delete; sets `deleted_at` and returns a deletion result.

Example create (fictional values):

```bash
curl -X POST http://localhost:8000/patients \
  -H 'Content-Type: application/json' \
  -d '{
    "first_name":"Taylor","last_name":"Demo-Sample","date_of_birth":"1991-06-15",
    "sex":"Other","phone_number":"202-555-0186","address_line_1":"99 Fictional Way",
    "city":"Springfield","state":"VA","zip_code":"22150"
  }'
```

Optional fields: `email`, `address_line_2`, `insurance_provider`, `insurance_member_id`, `preferred_language` (defaults to `English`), `emergency_contact_name`, and `emergency_contact_phone`. Required fields and enumerations are validated by the API even when called outside Vapi.

## Automated tests

```bash
pip install -r requirements.txt
pytest -q
```

The tests use an isolated in-memory SQLite database and fictional values; they cover create/read, all supported filters, UUID lookup, partial update, soft deletion, validation failures, duplicate lookup, envelopes, and sanitized database errors.

### Local-readiness audit (2026-10-27)

- Python: 3.14.3 (meets the 3.12+ requirement).
- Installed versions in `.venv`: FastAPI 0.162.0, Starlette 1.10.0, SQLAlchemy 2.1.6, Pydantic 2.14.1, pydantic-settings 2.16.1, psycopg/psycopg-binary 3.3.6, Uvicorn 0.54.0, HTTPX 0.28.1, pytest 8.4.2, email-validator 2.3.0, python-dotenv 1.2.4. `pip check` reports no broken requirements, and `pip install --dry-run --no-index -r requirements.txt` confirms every declared requirement is already installed.
- `python -m pytest -q`: 15 passed. Starlette emits a deprecation warning because its current TestClient prefers `httpx2`; plain `httpx` still works in the installed environment. No tests contact a network service or use provider credentials.
- No usable pip cache was available: pip disables the configured cache directory because it is not writable by this user. The tests ran from already installed virtualenv packages.
- No `.git` directory exists in this workspace, so the Git index could not be checked. `.gitignore` excludes `.env`; `.env.example` contains only blank credential fields. Review Git status after placing this project in its repository.
- PostgreSQL, Supabase, Render, Vapi, telephony, and a real phone call remain unconfigured and unverified.

## Vapi assistant and phone setup

The official Vapi Function tool protocol is used because the backend must validate the model-generated arguments, check for an existing phone number, and return a correlated result. The function schemas are generated by this repository:

```bash
PUBLIC_API_BASE_URL=https://your-service.onrender.com python scripts/export_vapi_tools.py
```

In the Vapi dashboard:

1. Create an assistant and select the Balanced preset (or configure the speech-to-text, model, and voice providers available to your account). Provider credentials and any usage billing are owned by your Vapi account.
2. Set the first message to: “Thanks for calling. I can help register your patient information. What name should I use?”
3. Paste the `SYSTEM_PROMPT` in `app/voice/vapi.py` into the assistant's system prompt. It instructs the assistant to collect required fields, offer optional fields, handle corrections, read back the record, and seek explicit permission before a write. This is prompt-level behavior; the backend does not independently verify caller speech.
4. Add the four Function tools generated above: `find_patient_by_phone`, `verify_patient_identity`, `create_patient_record`, and `update_patient_record`. The generated schemas include the webhook URL and tool descriptions. Keep synchronous execution enabled.
5. Add Vapi's built-in Hang Up tool. Keep its name `end_call_tool`, and set its Request Start goodbye to “Thanks for calling. Goodbye.” The system prompt tells the assistant to ask whether the caller needs anything else, then call this tool when the caller is done.
6. Set a public HTTPS server URL ending in `/vapi/webhook`; set `PUBLIC_API_BASE_URL` in Render first, then regenerate the tool JSON. The current URL is embedded in the output.
7. Create a Vapi Custom Credential using Bearer Token authentication and the same value as `VAPI_SERVER_SECRET`; attach it to the Function tool server. If no secret is set in the backend, the webhook accepts unauthenticated requests; set a strong random secret for a public deployment.
8. Publish the assistant. Under Phone Numbers, provision a U.S. number (or import one from a supported provider) and attach the assistant for inbound calls. Vapi documents its first free number as inbound-only; number availability and payment prompts depend on account and region.
9. Call the number with fictional data. Check Vapi call/webhook logs, then verify the record through the API. Test a correction, an invalid DOB/phone, a duplicate phone, a rejected save, and a database failure before sharing the number.

Vapi API Request tools directly call a REST endpoint; this project instead uses Function tools, so the Vapi tool calls arrive at `/vapi/webhook` with a `tool-calls` message and are answered in `results[]`. Tool payloads are validated again by Pydantic. The webhook returns success only after the database commit succeeds.

Provider references: [Vapi Function tools](https://docs.vapi.ai/tools/custom-tools), [server credentials](https://docs.vapi.ai/server-url/server-authentication), [Hang Up tool](https://docs.vapi.ai/tools/hang-up), and [assistant and inbound number quickstart](https://docs.vapi.ai/assistants/quickstart).

## Render and Supabase deployment

1. Create a Supabase project. Copy its PostgreSQL connection URI and follow Supabase guidance for direct or pooler connections and SSL. Keep credentials private.
2. Push this repository to GitHub/GitLab. In Render, create a Blueprint from the repository (uses `render.yaml`) or create a Python web service with build command `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`, and health path `/health`. Access logs are disabled because query filters can contain DOBs or phone numbers.
3. Set `DATABASE_URL` to the Supabase PostgreSQL URI, `PUBLIC_API_BASE_URL` to the final Render HTTPS URL, and set a strong `VAPI_SERVER_SECRET`. Render can generate `API_KEY`; retain it for REST API calls. Ensure Supabase networking permits the Render service.
4. Deploy and verify `GET https://<render-host>/health`. Configure the Vapi assistant tool webhook against the final URL and attach the Vapi credential. A service restart must still show prior records.
5. Set `API_BASE_URL` (and `API_KEY` when enabled) and run `python scripts/smoke_test.py`. It creates a fictional record, reads it, and soft-deletes it.
6. Confirm deployed tests locally with `pytest -q`, place an inbound test call, and share the repository URL, U.S. phone number, API base URL, and reviewer notes.

`render.yaml` requests generated secrets and leaves database URL and public service URL for the owner to set. Do not add secrets to the repository. Tables are created automatically at application startup; backups and production migrations are not configured.

## Vercel deployment

Vercel detects the FastAPI instance exported as `app` from `app/main.py`; this is a supported entrypoint under the `app/` directory. No `vercel.json`, `/api` wrapper, build command, output directory, Uvicorn start command, or `PORT` setting is needed. `render.yaml` remains for the previous Render setup and is not used by Vercel.

1. Push the repository to GitHub, then import it into Vercel as a new project. Keep the project root at the repository root.
2. Leave the Build Command and Output Directory at their Vercel defaults; Vercel installs the packages from `requirements.txt`. `.python-version` pins the runtime to Python 3.14.
3. In **Project Settings → Environment Variables**, add the following for Production (and Preview/Development only when needed):
   - `APP_ENV` = `production`
   - `DATABASE_URL` = the existing Supabase PostgreSQL connection URL
   - `PUBLIC_API_BASE_URL` = the Vercel HTTPS URL assigned to the project, such as `https://your-project.vercel.app`
   - `VAPI_SERVER_SECRET` = a strong secret; set the matching Vapi Bearer Token credential separately in Vapi
   - `API_KEY` = optional but recommended if clients use the REST `/patients` routes
4. Redeploy after adding or changing environment variables. Vercel functions have no persistent writable project filesystem; production startup rejects SQLite, and patient data remains in Supabase. Each function instance creates one SQLAlchemy engine with a one-connection pool. Startup still calls `create_all()` to create missing tables; it is not a migration mechanism.
5. Check `https://<your-project>.vercel.app/health`, then test patient routes with fictional data. Update the Vapi Function server URL to `https://<your-project>.vercel.app/vapi/webhook`, configure its Bearer Token credential to match `VAPI_SERVER_SECRET`, and regenerate tool JSON with `PUBLIC_API_BASE_URL` set to the Vercel URL.

No Vercel-specific build or deployment file is needed for this project. Hobby plan function limits are sufficient for these synchronous API requests; Vercel's plan terms and current account usage still apply.

## Limitations and next steps

- A public, dialable number, live assistant, hosting service, and Supabase project are not provisioned by this repository. Those account, credential, billing, and publication steps require the owner.
- No authentication is required on REST routes when `API_KEY` is blank; configure it before making the API public.
- Duplicate lookup keys on phone number and offers identity verification by name and DOB. The later update call is not cryptographically or transactionally bound to the verified lookup; do not rely on this flow for real patient records.
- No rate limiting, audit system, schema migrations, encryption policy, backups, consent recording, or HIPAA compliance is provided.
- The API keeps optional demographic details only when volunteered. No full payload logging or call transcripts are retained to limit exposure of personal data.
- A privacy-conscious observability event should record an opaque request/call ID, event type, success/failure, duration, validation outcome, and which fields were present, without the field values; restrict access and retention. Current logs record operation and patient UUID only.
- Follow-up work: enforce caller confirmation beyond a model-generated flag, bind duplicate updates to verified identity, add Alembic migrations, structured redacted audit events, deployment monitoring, additional call simulations, and a privacy/security review for any real deployment.
