from pydantic import BaseModel
import requests
from typing import List
import json
from utils.config import config
from utils.security import decrypt
from utils.log import log
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
from server.response import RequestError

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


def get_page_product_nums(current):
    uux_url = config['uux_url']
    url = f'https://{uux_url}/mcsp/productAi/page'
    product_nums = []
    data = requests.get(url, params={'current': current}).json()['data']
    if data is not None and 'records' in data.keys() and data['records'] is not None:
        for record in data['records']:
            if record['productNum'] not in product_nums:
                product_nums.append(record['productNum'])
    return product_nums

def get_product_feature(product_num):
    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config['coze_product_feature_wf_id'],
        "parameters": {
            "product_num": product_num,
            "env": config['env']
        }
    }
    response = requests.post(url, headers=headers, json=data)
    product_detail = ''
    if response.status_code == 200:
        response_data = response.json()
        input_data = response_data["data"]
        try:
            parsed_data = json.loads(input_data)
            product_detail = parsed_data['product_feature']
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    return product_detail


def process_page(current):
    id = config['kb_id']

    try:
        product_nums = get_page_product_nums(current)
    except Exception as e:
        print(e)

    files = []
    result = ''

    for product_num in product_nums:
        retrys = 0
        while retrys < 3:
            try:
                product_feature = get_product_feature(product_num)
                if product_feature is None or product_feature == '':
                    raise RuntimeError('detail empty')
                file_content = product_feature
                file_name = product_num + ".txt"
                files.append(('files', (file_name, file_content.encode('utf-8'))))
                break
            except Exception as exc:
                result += f'retry:{retrys}/{current}/{product_num}/{exc};'
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
        with ThreadPoolExecutor(max_workers=2) as executor:
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