import uuid

from dns.e164 import query
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
import time

from data.search import SearchEntity, ProductsEntity
from utils.config import config
from utils.security import decrypt
from server.response import RequestError
from datetime import datetime, timedelta
from utils.retrieve import retrieve


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
    taskId: str

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


def get_task_id(request: ProductSearchRequest):
    task_id = str(uuid.uuid4())
    SearchEntity.create(task_id=task_id, maxNum=request.maxNum, messages=json.dumps(request.messages, ensure_ascii=False, indent=4))
    return task_id

def get_query_message(messages, n=10):
    turns = []
    # 逆序遍历，填充对话轮次
    for msg in reversed(messages):
        if msg["role"] == "user":
            turns.append(msg)
        elif turns and turns[-1]["role"] == "user":  # 当前是AI且上一条是用户
            turns.append(msg)
        if len(turns) >= 2 * n:  # 每轮含用户+AI两条消息
            break
    # 恢复时间顺序并拼接
    turns_ordered = reversed(turns)
    return "\n".join(msg["content"] for msg in turns_ordered if msg.get("content"))



async def get_summary(task_id: str):
    request = SearchEntity.query_first(task_id=task_id)
    messages = request.messages
    query_message = get_query_message(messages)
    recent_messages = request.messages[-21:]

    retrieve(query=query_message, top_k=request.maxNum)

    # 使用多进程（注意，不是线程）并发调用 llm.generate 和 llm.stream_generate

def get_products(task_id: str):
    start_time = datetime.now()
    timeout = timedelta(seconds=120)
    poll_interval = 3  # seconds

    while datetime.now() - start_time < timeout:
        products_entity = ProductsEntity.query_first(task_id=task_id)
        if products_entity:
            products = json.loads(products_entity.products)
            if isinstance(products, str):
                products = json.loads(products)
            return ProductsResponse(products=products)

        # Wait before trying again
        time.sleep(poll_interval)

    # If we get here, we timed out
    return ProductsResponse(products=None)
