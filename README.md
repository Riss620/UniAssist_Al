# UniAssist AI — University Student Support System

A responsive student-support web app with accounts, multi-specialist routing, chat history, PDF uploads/retrieval, and a study task planner. It supports a zero-key local mode and an optional live LLM mode using an Azure OpenAI / OpenAI-compatible endpoint.

## Requirements
- Windows 10/11 or macOS/Linux
- Python 3.10+
- Internet for first-time package installation

## Run locally (no API key)
1. Extract the ZIP.
2. On Windows, double-click `run_windows.bat`. Alternatively:
   ```bash
   python -m venv .venv
   # Windows: .venv\\Scripts\\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # on Windows: copy .env.example .env
   uvicorn app.main:app --reload
   ```
3. Open http://127.0.0.1:8000 and create an account.

## Enable live AI
1. Install optional integrations: `pip install -r requirements-ai.txt`.
2. Edit `.env` and set `AI_MODE=auto`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_DEPLOYMENT`.
3. The endpoint should be your Azure OpenAI resource endpoint, for example `https://YOUR-RESOURCE.openai.azure.com`. The configured deployment name must match a deployed chat model.
4. Restart the app. Visit `/health`; `ai_configured` should be `true`.
5. Never commit `.env` or share API keys in screenshots/chat.

For a non-Azure OpenAI-compatible provider, set `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` instead. Check the provider's expected base URL format. This code uses the OpenAI-compatible `/openai/v1` path for Azure resource endpoints.

## Features
- Registration/login with PBKDF2 password hashing and server-side revocable sessions
- Specialist routing: Academic Advisor, Study Planner, Document Researcher, Student Support, Coordinator
- Optional live LLM responses with chat context
- Text-based PDF extraction and per-user document storage
- Student task planner with due dates and completion state
- Responsive desktop/mobile UI
- Docker deployment with persistent SQLite volume

## API
- `GET /health`
- `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/me`
- `POST /api/chat`, `GET /api/history`
- `POST /api/documents`, `GET /api/documents`, `DELETE /api/documents/{id}`
- `GET /api/tasks`, `POST /api/tasks`, `PATCH /api/tasks/{id}`
- Interactive API docs: `/docs`

## Test
```bash
pip install -r requirements.txt pytest
pytest -q
```

## Important scope and limitations
- The optional live mode is a single LLM call guided by specialist prompts and deterministic routing. It is **not** yet an AutoGen GroupChat runtime or a full Semantic Kernel orchestration pipeline. The optional framework packages are listed for the next integration milestone, not falsely represented as active runtime dependencies.
- PDF retrieval is keyword-based and extracts selectable text; scanned/image-only PDFs need OCR, which is not included.
- SQLite is suitable for a student demo/small prototype. For a real university deployment, use managed PostgreSQL, HTTPS, secret management, backups, rate limiting, audit logs, stronger admin provisioning, and institutional privacy/security review.
- Local fallback is rule-guided and will not provide general LLM reasoning.
