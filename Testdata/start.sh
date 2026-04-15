#!/bin/bash

# 1. Get Local IP
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "Starting System on IP: $IP_ADDR"

# 2. Start Backend (Flask) in the background
cd backend
source venv/bin/activate # Remove if not using venv
export FLASK_ENV=development
python3 app.py & 
BACKEND_PID=$!

# 3. Start Frontend (HTTP Server)
cd ../frontend
python3 -m http.server 5500 &
FRONTEND_PID=$!

echo "--------------------------------------"
echo "FRONTEND: http://$IP_ADDR:5500"
echo "BACKEND:  http://$IP_ADDR:5001"
echo "--------------------------------------"
echo "Press CTRL+C to stop both servers."

# Wait for exit to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait