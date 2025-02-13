from pydantic import BaseModel
import requests
from typing import List
import json
from utils.config import config
from utils.security import decrypt
from utils.log import log
from server.response import RequestError
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

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
    product_ids = []
    data = requests.get(url, params={'current': current}).json()['data']
    if data is not None and 'records' in data.keys() and data['records'] is not None:
        for record in data['records']:
            if record['productNum'] not in product_nums:
                product_nums.append(record['productNum'])
                product_ids.append(record['productId'])
    return product_nums, product_ids

def get_product_detail(product_id):
    uux_url = config['uux_url']
    url = f'https://{uux_url}/mcsp/productAi/productInfo?productId={product_id}'
    response = requests.get(url).json()['data']
    product_detail = json.dumps(response, ensure_ascii=False)
    return product_detail


def process_page(current):
    id = config['kb_id']

    product_nums, product_ids = get_page_product_nums(current)
    files = []
    result = ''

    for product_num, product_id in zip(product_nums, product_ids):
        try:
            product_detail = get_product_detail(product_id)
            if product_detail is None or product_detail == '':
                raise RuntimeError('detail empty')
            file_content = product_detail
            file_name = product_num + ".txt"
            files.append(('files', (file_name, file_content.encode('utf-8'))))
        except Exception as exc:
            result += f'{current}/{product_num}/{exc};'

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