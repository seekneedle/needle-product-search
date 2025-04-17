#!/bin/bash

port=8409
# 查找监听 ${port} 端口的进程 PID
pid=$(lsof -i :${port} | sed '1d' | awk '{print $2}')

# 如果找到了 PID，则尝试杀死进程
if [[ -n ${pid} ]]; then
    echo "stopping application with PID ${pid} ..."
    kill $pid
    echo "application stopped."
else
    echo "no process found listening on port ${port}"
fi
