#!/bin/bash
# start-dev.sh

# Start backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Handle shutdown
trap "kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT SIGTERM
wait