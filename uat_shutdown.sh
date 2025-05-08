#!/bin/bash

pid=$(lsof -i :8405 | awk 'NR>1 {print $2}')

echo "pid: $pid"

if [ -n "$pid" ]; then
    echo "Stopping application with PID $pid..."
    kill $pid
    echo "Application stopped."
else
    echo "No process found listening on port 8405."
fi
