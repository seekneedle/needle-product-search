import uuid

from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
import random

from data.search import SearchEntity, ProductsEntity
from utils.config import config
from utils.security import decrypt
from server.response import RequestError


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

async def get_summary(task_id: str):
    request = SearchEntity.query_first(task_id=task_id)
    url = config['coze_stream_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config['coze_product_search_stream_wf_id'],
        "parameters": {
            "env": config['env'],
            "max_num": request.maxNum,
            "messages": json.loads(request.messages)
        }
    }

    response = requests.post(url, headers=headers, json=data, stream=True)
    products = []
    if response.status_code == 200:
        try:
            # 由于您的数据看起来是以换行符分隔的JSON对象，我们可以逐行读取
            for line in response.iter_lines():
                # 过滤掉空的行以及以b'id:'或b'event:'开头的行
                if line and not (line.startswith(b'id:') or line.startswith(b'event:')):
                    decoded_line = line.decode('utf-8')

                    # 去除'data: '前缀
                    if decoded_line.startswith('data: '):
                        decoded_line = decoded_line[len('data: '):]

                    # 确保decoded_line是一个有效的JSON字符串
                    if decoded_line.strip():  # 检查是否为空字符串
                        try:
                            event_data = json.loads(decoded_line)

                            content = event_data.get('content')
                            if "\n\n" == content:
                                continue
                            if "\n\n" in content:
                                content = content.replace("\n\n", "\n")
                            if content:
                                if "<sep>" in content:
                                    if not products:
                                        outputs = content.split("<sep>")
                                        products.append(outputs[1])
                                        yield f"data: {outputs[0]}\n\n"
                                        if len(outputs) == 3:
                                            products = json.dumps("".join(products), ensure_ascii=False, indent=4)
                                            ProductsEntity.create(task_id=task_id, products=products)
                                            break
                                    else:
                                        outputs = content.split("<sep>")
                                        products.append(outputs[0])
                                        products = json.dumps("".join(products), ensure_ascii=False, indent=4)
                                        ProductsEntity.create(task_id=task_id, products=products)
                                        break
                                else:
                                    if not products:
                                        yield f"data: {content}\n\n"
                                    else:
                                        products.append(content)
                        except json.JSONDecodeError as e:
                            # 打印详细的错误信息，便于调试
                            raise RequestError(response.status_code,
                                               f"无法解析的JSON行: {decoded_line}, 错误: {e}")
                    else:
                        raise RequestError(response.status_code,
                                           f"忽略空行或无效行: {decoded_line}")
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    else:
        raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")

def get_products(task_id: str):
    products_entity = ProductsEntity.query_first(task_id=task_id)
    products = json.loads(products_entity.products)
    if isinstance(products, str):
        products = json.loads(products)
    if config["env"] == "uat":
        mock_product_nums = [
            "U167127", "U167125", "U167418", "U167421", "U167800", "U167197",
            "U167142", "U167070", "U167761", "U167502", "U167501", "U167497",
            "U167070", "U167753", "U167284", "U167148", "U167149", "U167069",
            "U167093", "U167460"
        ]

        # 随机选择与 products 个数相同的 productNum
        selected_product_nums = random.sample(mock_product_nums, len(products))

        # 更新 products 中的 productNum 字段
        for i, product in enumerate(products):
            product["productNum"] = selected_product_nums[i]

    return ProductsResponse(products=products)