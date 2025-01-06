
from pydantic import BaseModel
import requests
from typing import List
import json


class ProductSearchRequest(BaseModel):
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True


class ProductSearchResponse(BaseModel):
    product_ids: List[str]


class RequestError(Exception):
    """自定义异常类，用于处理请求错误"""
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def product_search(request: ProductSearchRequest):
    url = 'https://api.coze.cn/v1/workflow/run'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer pat_w9Ix9RRMfMjmN4ZTIXFIXJ0qL6yBQW2hDG0rsYelpr6fv9dLpCzYtZfZfKLB2pww'
    }
    data = {
        "workflow_id": "7454405767978926091",
        "parameters": {
            "messages": request.messages
        }
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        input_data = response_data["data"]
        try:
            parsed_data = json.loads(input_data)
            response = ProductSearchResponse(**parsed_data)
            return response
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    else:
        raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")