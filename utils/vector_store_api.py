import requests
import json
from utils.config import config
from utils.log import log


# api: 形如 '/file/list_batch'
# data: 形如 {'file_names': ['U167478', 'U167490']}

def post_call(api: str, data: dict):
    needle_url = config['needle_url']
    url = f'{needle_url}/vector_store{api}'
    log.info(f'vector_store_api post {url} data={data}')

    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='
    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }

    data['id'] = config['kb_id']       # for /file/delete
    data['index_id'] = config['kb_id'] # for /file/list_batch
    # 在传进来的 data 对象中加上 index_id。最终形如：
    # data = {
    #     'index_id': index_id,
    #     'file_names': product_nums
    # }
    response = requests.post(url, headers=headers, json=data)
    if response is None:
        return []
    return response.json()['data']
    # 调用者再从返回对象中取出感兴趣的字段


def file_add(files):
    needle_url = config['needle_url']
    url = f'{needle_url}/vector_store/file/add'
    log.info(f'vector_store_api.file_add {url}')

    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='
    headers = {
        'Authorization': auth
    }
    
    add_data = {
        'id': config['kb_id']
    }
    response = requests.post(url, headers=headers, data=add_data, files=files)
    return response.text if response else 'unknown'
