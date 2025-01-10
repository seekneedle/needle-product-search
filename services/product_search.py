
from pydantic import BaseModel
import requests
from typing import List
import json
from utils.config import config
from utils.security import decrypt


class ProductSearchRequest(BaseModel):
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True


class ProductSearchResponse(BaseModel):
    content: str
    product_details: List[str]
    product_features: List[str]


class RequestError(Exception):
    """自定义异常类，用于处理请求错误"""
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def product_search(request: ProductSearchRequest):
    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": decrypt(config['coze_product_search_wf_id']),
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