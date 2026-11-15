@echo off
cd /d %~dp0
if not exist .venv (py -m venv .venv)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-ai.txt
if not exist .env copy .env.example .env
echo Edit .env and set Azure endpoint, key and deployment before using live mode.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
