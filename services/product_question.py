
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
from utils.config import config
from utils.security import decrypt
from server.response import RequestError


class ProductQuestionRequest(BaseModel):
    is_uux: Optional[int] = 0
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True


class ProductQuestionResponse(BaseModel):
    questions: List[object] # todo: or string?


def product_question(request: ProductQuestionRequest):
    if request.is_uux != 0:
        parsed_data = {'questions': [
            '这条线每日具体行程安排是怎样的？',
            '这条线的费用包含哪些项目？',
            '这条线旅行过程中有哪些适合团队合作的活动？'
        ]}
        response = ProductQuestionResponse(**parsed_data)
        return response

    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config['coze_product_questions_wf_id'],
        "parameters": {
            "env": config['env'],
            "messages": request.messages
        }
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        input_data = response_data["data"]
        try:
            parsed_data = json.loads(input_data)
            response = ProductQuestionResponse(**parsed_data)
            return response
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    else:
        raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")