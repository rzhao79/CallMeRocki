To run this service:
- Download Python
- CD into CallMeRocki
- python -m venv .venv
- ./.venv/Scripts/Activate.ps1 (or Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass .\.venv\Scripts\Activate.ps1)
- pip install -e
- Configure the env file
- Start the server with uvicorn main:app --app-dir src --host 0.0.0.0 --port 8787 --reload