from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
import requests
from utils.config import config
import json
import base64
from utils.security import sha256_encode

app = FastAPI()


# 创建安全实例
security = HTTPBasic()


def verify_credentials(cre_username, cre_password):
    username = config['username']
    password = config['password']
    if cre_username == username and sha256_encode(cre_password) == password:
        return True
    return False


# 检查操作权限
def check_permission(credentials: HTTPBasicCredentials = Depends(security)):
    if not verify_credentials(credentials.username, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )
