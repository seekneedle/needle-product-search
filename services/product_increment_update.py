import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

from pydantic import BaseModel
from typing import List

from utils.config import config
from utils.security import decrypt
from utils.log import log
from utils import coze, update_helper, vector_store_api
from server.response import RequestError
import requests

class ProductUpdateIncrRequest(BaseModel):
    # type: str
    productNums: List[str]
    class Config:
        arbitrary_types_allowed = True

class ProductUpdateIncrResponse(BaseModel):
    results: List[str]

def process_add_batch(product_nums):
    log.info(f'/incr_update add_batch {product_nums} begins')
    t00 = datetime.now()

    files = []
    with ThreadPoolExecutor(max_workers=len(product_nums)) as executor:
        futures = {executor.submit(update_helper.get_product_feature_for_update, pn): pn for pn in product_nums}
        for f in as_completed(futures):
            product_num = futures[f]
            try:
                if f.result() == '': # 出错，只能跳过，无其他办法
                    continue
                product_feature = f.result()
                if product_feature is None or product_feature == '':
                    continue
                file_content = product_feature # 内容太多，就不往 log 里打了
                file_name = product_num + ".txt"
                # files 对应的 value 是 (str, str) tuple，不是特殊数据类型
                files.append(('files', (file_name, file_content.encode('utf-8'))))
            except Exception as e:
                log.info(f'/incr_update add_batch {product_num} get_product_feature {e}')

    result = '' if len(files) == 0 else vector_store_api.file_add(files)
    log.info(f'/incr_update batch_add {product_nums} cost {datetime.now() - t00} result:{result}')
    return result

def get_file_ids(product_nums):
    data = {
        'file_names': product_nums
    }
    api_name = '/file/list_batch'
    key = 'documents'
    res = vector_store_api.post_call(api_name, data)
    return res[key] if key in res else []

def delete_files(file_ids):
    data = {
        'file_ids': file_ids
    }
    api_name = '/file/delete'
    key = 'file_ids' # deleted file ids
    res = vector_store_api.post_call(api_name, data)
    return res[key] if key in res else []

def product_increment_update(request: ProductUpdateIncrRequest):
    log.info(f'/incr_update product_increment_update {request} begins')
    t00 = datetime.now()

    product_nums = request.productNums
    if len(product_nums) == 0:
        return ProductUpdateIncrResponse(results=[])

    log.info(f'/incr_update {product_nums} get_file_ids() begins')
    files = get_file_ids(product_nums) # 只返回存在的 (doc_id, doc_name) 列表
    log.info(f'/incr_update {product_nums} file infos:{files}')

    # 存在的 file_id
    file_ids = [f['doc_id'] for f in files]
    # 存在的 names。用 set 去重。
    exist_name_set = set(f['doc_name'] for f in files)
    # 存在的 doc，doc_id -> doc_name 的 map
    file_id_names = {f['doc_id']:f['doc_name'] for f in files}
    # 不存在的 names
    non_exist_name_set = set(product_nums) - exist_name_set

    log.info(f'/incr_update {product_nums} exist file_ids:{file_ids}')
    log.info(f'/incr_update {product_nums} exist names: {exist_name_set}')
    log.info(f'/incr_update {product_nums} map: {file_id_names}')
    log.info(f'/incr_update {product_nums} non-exist names: {non_exist_name_set}')

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

    log.info(f'/incr_update {product_nums} deleted_ids:{deleted_ids}')
    log.info(f'/incr_update {product_nums} undeleted_names: {undeleted_name_set}')
    log.info(f'/incr_update {product_nums} delete_names: {deleted_name_set}')
    log.info(f'/incr_update {product_nums} final_names: {final_names}')

    ## 去掉 del 逻辑
    # if update_type == 'del':
    #     return ProductUpdateIncrResponse(results=final_names)

    uux_url = config['uux_url']
    valid_products = []

    for product_num in final_names:
        url = f'https://{uux_url}/mcsp/productAi/productInfo?productNum={product_num}'
        try:
            response = requests.get(url)
            response.raise_for_status()
            pf = response.json()['data']

            if (pf['openState'] == 1 and
                    pf['contractStatus'] == 1 and
                    pf['supplierStatus'] == 1 and
                    pf['auditStatus'] == 2):
                valid_products.append(product_num)
        except (requests.RequestException, KeyError) as e:
            log.error(f"Error processing product {product_num}: {e}")
            continue

    final_names = valid_products

    # 要 add 的：彻底删干净的 name，和本来就不存在的 name
    if len(final_names) == 0:
        return ProductUpdateIncrResponse(results=[])

    log.info(f'/incr_update after delete final_names: {final_names}')

    bsize = 10
    batches = [final_names[i:i + bsize] for i in range(0, len(final_names), bsize)]
    added_names = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        # map<future, to_add_name_list>
        futures = {executor.submit(process_add_batch, b): b for b in batches}

        for f in as_completed(futures):
            try:
                j = json.loads(f.result())
                j['data']['taskId'] = j['data'].pop('task_id') # 字段名驼峰化
                added_names.append(json.dumps(j))
            except Exception as e:
                trace_info = traceback.format_exc()
                prod_nums = futures[f]
                info = f'/incr_update add_batch {prod_nums} exception, e:{e}, trace: {trace_info}'
                log.error(info)
                added_names.append(info)

    response = ProductUpdateIncrResponse(results=added_names)
    log.info(f'/incr_update api request {product_nums} costs {datetime.now() - t00}, response:{response}')
    return response
