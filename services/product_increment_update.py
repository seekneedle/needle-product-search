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

class ProductUpdateIncrRequest(BaseModel):
    type: str
    productNums: List[str]
    class Config:
        arbitrary_types_allowed = True

class ProductUpdateIncrResponse(BaseModel):
    results: List[str]


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
            raise RequestError(response.status_code, f'解析失败: {response.status_code}, 响应内容: {response.text}')
    return product_detail


def process_add_batch(product_nums):
    index_id = config['kb_id']
    needle_url = config['needle_url']
    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='
    headers = {
        'Authorization': auth
    }

    files = []
    result = ''

    for product_num in product_nums:
        retries = 0
        while retries < 3:
            try:
                product_feature = get_product_feature(product_num) # 调用 coze wf 得到
                if product_feature is None or product_feature == '':
                    raise RuntimeError('detail empty')
                file_content = product_feature
                file_name = product_num + ".txt"
                # files 对应的 value 是 (str, str) tuple，不是特殊数据类型
                files.append(('files', (file_name, file_content.encode('utf-8'))))
                break
            except Exception as e:
                current = 0
                result += f'retry:{retries}/current:{current}/{product_num}/{e};'
                retries += 1

    url = f'{needle_url}/vector_store/file/add'
    add_data = {
        'id': index_id
    }
    response = requests.post(url, headers=headers, data=add_data, files=files)
    if response is not None and result == '':
        result = response.text

    return result

def get_file_ids(product_nums):
    needle_url = config['needle_url']
    url = f'{needle_url}/vector_store/file/list_batch'

    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='
    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }

    index_id = config['kb_id']
    data = {
        'index_id': index_id,
        'file_names': product_nums
    }
    response = requests.post(url, headers=headers, json=data)
    if response is None:
        return []
    return response.json()['data']['documents']

def delete_files(file_ids):
    needle_url = config['needle_url']
    url = f'{needle_url}/vector_store/file/delete'

    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='
    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }

    index_id = config['kb_id']
    del_data = {
        'id': index_id,
        'file_ids': file_ids
    }
    response = requests.post(url, headers=headers, json=del_data)
    if response is None:
        return []

    deleted_nums = response.json()['data']['file_ids'] # deleted file ids
    return deleted_nums

def product_increment_update(request: ProductUpdateIncrRequest):
    update_type = request.type
    product_nums = request.productNums

    if len(product_nums) == 0:
        return ProductUpdateIncrResponse(results=[])

    files = get_file_ids(product_nums) # 只返回存在的 (doc_id, doc_name) 列表

    # 存在的 file_id
    file_ids = [f['doc_id'] for f in files]
    # 存在的 names。用 set 去重。
    exist_name_set = set(f['doc_name'] for f in files)
    # 存在的 doc，doc_id -> doc_name 的 map
    file_id_names = {f['doc_id']:f['doc_name'] for f in files}
    # 不存在的 names
    non_exist_name_set = set(product_nums) - exist_name_set

    # log.info(f'_incr: exist file_ids:{file_ids}')
    # log.info(f'_incr: exist names: {exist_name_set}')
    # log.info(f'_incr: map: {file_id_names}')
    # log.info(f'_incr: non exist names: {non_exist_name_set}')

    # 删掉的 file_ids
    # 若所有 file_id 都不存在，不用删，直接设为 []；否则，设为 delete_files() 的结果
    deleted_ids = [] if len(file_ids) == 0 else delete_files(file_ids)
    # 未（完全）删掉的 names
    undeleted_name_set = set(file_id_names[fid] for fid in (set(file_ids) - set(deleted_ids)))
    # 完全删掉（对应的所有 doc_id/file_id 都删了）的 names
    deleted_name_set = exist_name_set - undeleted_name_set

    # 一个 product_name/file_name/doc_name 可能对应多个 doc_id
    # 只有所有 doc_id 都被删掉，才认为该 product_name/file_name/doc_name 被删掉

    # 若是「删除」请求，把「不存在的」也放到「返回」列表里
    # 若是「新增」请求，把「不存在的」也放到「待新增」列表里
    final_names = list(set.union(deleted_name_set, non_exist_name_set))

    # log.info(f'_incr: deleted_ids:{deleted_ids}')
    # log.info(f'_incr: undeleted_names: {undeleted_name_set}')
    # log.info(f'_incr: delete_names: {deleted_name_set}')
    # log.info(f'_incr: final_names:: {final_names}')

    if update_type == 'del':
        return ProductUpdateIncrResponse(results=final_names)

    # 要 add 的：彻底删干净的 name，和本来就不存在的 name
    if len(final_names) == 0:
        return ProductUpdateIncrResponse(results=[])

    bsize = 10
    batches = [final_names[i:i + bsize] for i in range(0, len(final_names), bsize)]
    added_names = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        # map<future, to_add_name_list>
        futures = {executor.submit(process_add_batch, b): b for b in batches}

        for f in as_completed(futures):
            try:
                added_names.append(f.result())
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for add_batch, e:{e}, prod_nums:{futures[f]}, trace: {trace_info}'
                log.error(info)
                added_names.append(info)
    return ProductUpdateIncrResponse(results=added_names)
