
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
from utils.config import config
from utils.security import decrypt
from server.response import RequestError
import time


class ProductSearchRequest(BaseModel):
    maxNum: Optional[int] = 5
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True


class ProductSearchResponse(BaseModel):
    summary: str
    products: List[object]
    classificationid: int


class ProductSearchTaskResponse(BaseModel):
    task_id: str

class ProductsResponse(BaseModel):
    products: List[object]


def product_search(request: ProductSearchRequest):
    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config['coze_product_search_wf_id'],
        "parameters": {
            "env": config['env'],
            "max_num": request.maxNum,
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


async def get_summary(task_id: str):
    for text in ["你好", "，", "向你", "推荐", "一款", "巴黎", "3天", "2晚", "的", "旅行", "产品", "，", "请问", "您", "感兴趣", "么", "？"]:
        time.sleep(0.2)
        yield f"data: {text}\n\n"