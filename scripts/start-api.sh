#!/bin/bash
set -e
cd /app/backend
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
