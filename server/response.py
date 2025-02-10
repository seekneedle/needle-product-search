from pydantic import BaseModel
from typing import TypeVar

# 定义一个类型变量 T，表示任何继承自 BaseModel 的子类
T = TypeVar('T', bound=BaseModel)


# 定义通用的响应模型
class SuccessResponse(BaseModel):
    code: int = 200
    status: str = 'success'
    data: T


class FailResponse(BaseModel):
    code: int = 400
    status: str = 'fail'
    error: str

class RequestError(Exception):
    """自定义异常类，用于处理请求错误"""
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
