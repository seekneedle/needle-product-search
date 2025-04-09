#!/bin/bash

# 查找监听 8410 端口的进程 PID
pid=$(lsof -i :8410 | awk 'NR>1 {print $2}')

# 如果找到了PID，则尝试杀死进程
if [ -n "$pid" ]; then
    echo "Stopping application with PID $pid..."
    kill $pid
    echo "Application stopped."
else
    echo "No process found listening on port 8405."
fi
