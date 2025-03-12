
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
from utils.config import config
from utils.security import decrypt
from server.response import RequestError


class ProductSearchRequest(BaseModel):
    max_num: Optional[int] = 5
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True


class ProductSearchResponse(BaseModel):
    summary: str
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
            "max_num": request.max_num,
            "messages": request.messages
        }
    }
    response = requests.post(url, headers=headers, json=data)
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
                            if content:
                                print(f"收到消息: {content}")
                        except json.JSONDecodeError as e:
                            # 打印详细的错误信息，便于调试
                            print(f"无法解析的JSON行: {decoded_line}, 错误: {e}")
                    else:
                        print(f"忽略空行或无效行: {decoded_line}")
            return response
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    else:
        raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")