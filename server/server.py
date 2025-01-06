import uvicorn
from utils.config import config
from fastapi import FastAPI
from server.product_router import store_router
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
# 包含路由
app.include_router(store_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config['origins'],  # 允许的来源
    allow_credentials=True,  # 是否允许凭证传输，如cookies等敏感信息
    allow_methods=['*'],     # 允许的方法，默认为['GET']
    allow_headers=['*'],     # 允许的头部，默认为空列表
)


def start_server():
    ip = config['ip']
    port = config['port']
    uvicorn.run(app, host=ip, port=port)
