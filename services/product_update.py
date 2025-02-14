from pydantic import BaseModel
import requests
from typing import List
import json
from utils.config import config
from utils.security import decrypt
from utils.log import log
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
from openai import OpenAI

class ProductUpdateResponse(BaseModel):
    results: List[str]

def delete_product_kb():
    id = config['kb_id']
    needle_url = config['needle_url']
    url = f"{needle_url}/vector_store/file/list/{id}"
    auth = "Basic bmVlZGxlOm5lZWRsZQ=="

    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }
    response = requests.get(url, headers=headers)
    file_ids = []
    for doc in response.json()['data']['documents']:
        file_ids.append(doc['doc_id'])
    if file_ids:
        url = f"{needle_url}/vector_store/file/delete"
        auth = "Basic bmVlZGxlOm5lZWRsZQ=="

        headers = {
            'Content-Type': 'application/json',
            'Authorization': auth
        }
        data = {
            "id": id,
            "file_ids": file_ids
        }
        requests.post(url, headers=headers, json=data)

def get_product_pages():
    uux_url = config['uux_url']
    url = f'https://{uux_url}/mcsp/productAi/page'
    data = requests.get(url).json()['data']
    if data is not None and 'pages' in data.keys():
        return data['pages']
    return 0


def get_page_product_ids(current):
    uux_url = config['uux_url']
    url = f'https://{uux_url}/mcsp/productAi/page'
    product_ids = []
    data = requests.get(url, params={'current': current}).json()['data']
    if data is not None and 'records' in data.keys() and data['records'] is not None:
        for record in data['records']:
            if record['productId'] not in product_ids:
                product_ids.append(record['productId'])
    return product_ids

def get_product_detail(product_id):
    uux_url = config['uux_url']
    url = f'https://{uux_url}/mcsp/productAi/productInfo?productId={product_id}'
    response = requests.get(url).json()['data']
    product_detail = json.dumps(response, ensure_ascii=False)
    return product_detail


def process_page(current):
    id = config['kb_id']

    try:
        product_ids = get_page_product_ids(current)
    except Exception as e:
        print(e)

    files = []
    result = ''

    for product_id in product_ids:
        retrys = 0
        while retrys < 3:
            try:
                product_detail = get_product_detail(product_id)[:3000]
                if product_detail is None or product_detail == '':
                    raise RuntimeError('detail empty')
                client = OpenAI(
                    api_key=decrypt(config['api_key']),
                    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                )
                prompt = f'''# 角色
    你是一个专业的旅行产品分析员，能够准确地从旅行产品详情中提取出产品特点。
    
    ## 技能
    ### 技能 1: 分析旅行产品特点
    1. 仔细阅读旅行产品详情。
    2. 根据产品详情，分析并总结出该产品的特点，如适合的人群（年纪较大、小孩儿童、蜜月旅行等）、价格特点（适合要求价格低的客户）、游玩地点特点（适合想在草原玩的客户）、活动类型特点（适合想要参加夏令营的客户等）、是否属于比较轻松的产品（比如每天前往的景点较少，或者基本都有交通工具）。
    ===回复示例===
       - 特点描述：<产品特点的具体描述>
       - 理由：<说明该特点的依据，从产品详情中提取>
    ===示例结束===
    
    ## 产品详情
    {product_detail}
    
    ## 限制:
    - 只分析旅行产品相关内容，拒绝回答与旅行产品无关的话题。
    - 所输出的内容必须按照给定的格式进行组织，不能偏离框架要求。'''
                messages = [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
                completion = client.chat.completions.create(
                    model="qwen-plus-2024-09-19",
                    messages=messages,
                    temperature=0.5
                )
                query_content = completion.choices[0].message.content
                file_content = query_content
                file_name = product_id + ".txt"
                files.append(('files', (file_name, file_content.encode('utf-8'))))
                break
            except Exception as exc:
                result += f'retry:{retrys}/{current}/{product_id}/{exc};'
                retrys += 1

    needle_url = config['needle_url']
    url = f"{needle_url}/vector_store/file/add"
    auth = "Basic bmVlZGxlOm5lZWRsZQ=="

    headers = {
        'Authorization': auth
    }
    data = {
        "id": id
    }
    response = requests.post(url, headers=headers, data=data, files=files)
    if response is not None and result == '':
        result = response.text

    return result

def product_update():
    pages = int(get_product_pages())
    if pages > 0:
        delete_product_kb()
        with ThreadPoolExecutor(max_workers=1) as executor:
            results = []
            # Create a dictionary to map futures to their corresponding product numbers for easy lookup later if needed
            future_to_page_num = {executor.submit(process_page, num): num for num in range(1, pages+1)}

            for future in as_completed(future_to_page_num):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    trace_info = traceback.format_exc()
                    page_num = future_to_page_num[future]
                    log.error(
                        f'Exception for get_product_details, page_num: {page_num}, e: {exc}, trace: {trace_info}')
                    results.append(f'Exception for get_product_details, page_num: {page_num}, e: {exc}, trace: {trace_info}')
        return ProductUpdateResponse(results=results)
    return ProductUpdateResponse(results=[])