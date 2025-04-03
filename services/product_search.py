import uuid

from dns.e164 import query
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
import time
from data.search import SearchEntity, SearchEntityEx, ProductsEntity
from utils.config import config
from utils.log import log
from utils.security import decrypt
from server.response import RequestError
from datetime import datetime, timedelta
from utils.retrieve import retrieve
from utils import coze
from utils import llm
from openai import OpenAI
import threading
import asyncio

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


def coze_call(wf_id, params):
    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config[wf_id],
        "parameters": params
    }
    log.info(f'__coze_call params: {params}')
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        log.info(f'__coze_call response: {response_data}')
        input_data = response_data["data"]
        try:
            parsed_data = json.loads(input_data)
            return parsed_data
            # response = ProductSearchResponse(**parsed_data)
            # return response
        except json.JSONDecodeError:
            raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    else:
        raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")


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


def retrieve_products_bg(task_id: str, request):
    tx = datetime.now()
    env = config['env']
    wf_id_name = 'coze_product_search_task_wf_id'
    params = {
        'env': env,
        'messages': request.messages
    }
    t0 = datetime.now()
    res = coze_call(wf_id_name, params)
    t1 = datetime.now()
    log.info(f'coze_call get_input_summary_and_condition costs {t1 - t0}.')
    log.info(res)
    max_num = request.maxNum
    user_input_summary = res['user_input_summary']
    condition = res['condition']
    log.info(user_input_summary)
    log.info(condition)

    rerank_top_k = max_num
    retries = 0
    t0 = datetime.now()
    while retries < 3:
        t1 = datetime.now()
        kb_res = coze.search_product_kb(user_input_summary, rerank_top_k, env)
        t2 = datetime.now()
        product_nums = kb_res['product_nums']
        dyna_res = coze.get_dynamic_features(product_nums, env)['products']
        t3 = datetime.now()
        log.info(f'coze_api: search_product_kb costs {t2 - t1}')
        log.info(f'coze_api: get_dynamic_features costs {t3 - t2}')
        remaining_product_nums = coze.filter_dynamic(condition, dyna_res)['product_nums']
        if len(remaining_product_nums) > 0:
            break
        rerank_top_k += max_num
        retries += 1
    t4 = datetime.now()
    log.info(f'batch: get_products overall costs {t4 - t0}')

    log.info(f'__remaining_product_nums:{remaining_product_nums}')
    t0 = datetime.now()
    prod_res = coze.get_product_features(remaining_product_nums, env)['products']
    log.info(f'coze_api: get_product_features costs {datetime.now() - t0}')
    product_infos = [{
        'product_num' : pn,
        'product_feature' : prod_res[pn]['product_feature'],
        'dynamic_feature' : dyna_res[pn]['product_feature'],
        'cals' : dyna_res[pn]['cals']
    } for pn in remaining_product_nums]
    log.info(f'__product_infos: {product_infos}')

    SearchEntityEx.create(
        task_id=task_id,
        max_num=max_num,
        messages=json.dumps(request.messages, ensure_ascii=False, indent=4),
        user_input_summary=user_input_summary,
        condition=json.dumps(condition, ensure_ascii=False, indent=4),
        product_infos=json.dumps(product_infos, ensure_ascii=False, indent=4)
    )
    log.info(f'get_task_id(), retrieve_products costs {datetime.now() - tx}')

def get_task_id(request: ProductSearchRequest):
    log.info(f'get_task_id(): request:{request}')
    task_id = str(uuid.uuid4())
    threading.Thread(target=retrieve_products_bg, args=(task_id, request)).start() # 启动后台线程
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


'''
coze workflow 的一些逻辑

批处理中，
    product_feature = product_feature + "\n" + str(dynamic_feature)
后两者分别来自 get_product_feature() 和 get_dynamic_feature()，
都已经是字符串（所以 dynamic_feature 其实没必要再 str() 一下）
注意: dynamic 中不含 cal（数字化的原始动态feature）

批处理之后，「按 score 排序且驼峰」中
先按 score 排序各产品，再把所有产品的 feature（批处理中已经拼接好的 product + dynamic）连接起来，
得到一个包括所有产品的静态、动态 feature 的大字符串
    product_features_str = "\n\n".join(product_features_sorted)
该大字符串，用于调用大模型得到 summary
'''

#
# 批处理中
#
# async def main(args: Args) -> Output:
#     params = args.params
#     product_feature = params["product_feature"]
#     dynamic_feature = params["dynamic_feature"]
#     content = params["content"]
#     product_num = params["product_num"]
#     score = params["score"]
#
#     # 构建输出对象
#     ret: Output = {
#         "product_feature": product_feature + "\n" + str(dynamic_feature),
#         "product": {
#             "content": content,
#             "score": score,
#             "product_num": product_num
#         },
#     }
#     return ret

#
# 批处理之后，「按 score 排序且驼峰」
#
# async def main(args: Args) -> Output:
#     params = args.params
#     products = params['products']
#     product_features = params['product_features']
#
#     # products 中每一项有三个字段：content, score, product_num
#     products_sorted = sorted(products, key=lambda p: -p['score'])
#
#     # product_features 中每一项是个字符串。该字符串是以换行符分割的多行内容。
#     # 其中第一行格式为 'productNum：U173757'，注意冒号是全角字符。
#     # 这里从其第一行取出 product_num 的值。
#     # map: product_num -> idx_in_dict>
#     d = {}
#     for i, p in enumerate(product_features):
#         pn = p.split('\n')[0].split('：')[-1]
#         d[pn] = i
#     # for i, p in enumerate(products):
#     #     pn = p['product_num']
#     #     d[pn] = i
#
#     product_features_sorted = [product_features[d[p['product_num']]] for p in products_sorted]
#     product_features_str = "\n\n".join(product_features_sorted)
#
#     products_cameled = [{'productNum' if k == 'product_num' else k:v for k,v in e.items()} for e in products_sorted]
#     # 构建输出对象
#     ret: Output = {
#         "products": products_cameled,
#         "product_features": product_features_str
#     }
#     return ret


async def get_summary(task_id: str):
    log.info(f'__get_summary() {task_id}')
    start_time = datetime.now()
    timeout = timedelta(seconds=120)
    poll_interval = 1  # seconds

    while datetime.now() - start_time <= timeout:
        request = SearchEntityEx.query_first(task_id=task_id)
        if request:
            log.info(f'/get_summary_result {task_id} costs {datetime.now() - start_time} for data ready')
            break
        await asyncio.sleep(poll_interval)

    if datetime.now() - start_time > timeout: # timed out
        yield 'data: 不好意思，似乎出了些问题，目前没有可以推荐的\n\n'
        return

    #
    # todo: 算 summary 时，用 user_input_summary 代替 recent_messaeges ?
    #
    # recent_messages = json.loads(request.messages)[-21:]
    user_input_summary = request.user_input_summary
    product_infos = json.loads(request.product_infos)
    # log.info(f'__user_input_summary: {user_input_summary}')
    # log.info(f'__product_infos: {product_infos}')

    # todo: 原版计算 summary 时，各产品是按 score 从高到低排序的，
    #       意味着计算 summary 要在 content/score 都算出来之后
    #       现在先不管这个

    full_features = "\n\n".join([p['product_feature'] + '\n' + p['dynamic_feature'] for p in product_infos])

    #
    # todo 优化这个 prompt
    #
    prompt = f'''
根据产品信息，简短回答客户问题，不要超过五百字。

### 限制
1. productNum 是产品的唯一标识，必须包含每个产品的 productNum。
2. 只要提及产品，无论之前是否出现过，都要重新给出产品的 productNum。
3. 但不要出现 "productNum" 这个英文词，要用"编号为某某的产品"这样的方式。

### 产品信息：

{full_features}

### 用户的需求：

{user_input_summary}
'''

    client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )
    messages = [
        {
            'role': 'user',
            'content': prompt
        }
    ]
    completion = client.chat.completions.create(
        model="qwen-plus-2024-09-19",
        messages=messages,
        stream=True,
        stream_options={"include_usage": True}
    )
    for chunk in completion:
        if len(chunk.choices) > 0:
            yield f"data: {chunk.choices[0].delta.content}\n\n"

    # yield from llm.stream_generate(prompt)

    # wf_id_name = 'coze_product_search_summary_wf_id'
    # params = {
    #     'env': config['env'],
    #     'recent_messages': recent_messages,
    #     'product_features': full_features
    # }
    # t0 = datetime.now()
    # res = coze_call(wf_id_name, params)
    # log.info(f'coze_api: get_summary() costs {datetime.now() - t0}')
    # log.info(f'__res: {res}')
    #
    # todo: res 写到 db 里？
    #

    # 使用多进程（注意，不是线程）并发调用 llm.generate 和 llm.stream_generate

async def get_products(task_id: str, timeout_secs: int):
    log.info(f'__get_products() {task_id}')
    start_time = datetime.now()
    timeout = timedelta(seconds=timeout_secs)
    poll_interval = 2  # seconds

    while datetime.now() - start_time <= timeout:
        products_entity = SearchEntityEx.query_first(task_id=task_id)
        if products_entity:
            log.info(f'/get_products_result {task_id} costs {datetime.now() - start_time} for data ready')
            break
        await asyncio.sleep(poll_interval)

    if datetime.now() - start_time > timeout: # timeout
        return ProductsResponse(products=[])

    prod_infos = json.loads(products_entity.product_infos)
    # log.info(f'__get_product_contents: input_summary:{products_entity.user_input_summary}')
    # log.info(f'__get_product_contents: product_infos:{prod_infos}')

    product_nums = [p['product_num'] for p in prod_infos]
    full_features = [p['product_feature'] + '\n' + p['dynamic_feature'] for p in prod_infos]
    wf_id_name = 'coze_product_search_contents_wf_id'
    params = {
        'env': config['env'],
        #
        # todo 待讨论。这里用 input_summary 取代了 recent_messages
        #
        'recent_messages': products_entity.user_input_summary,
        'product_nums': product_nums,
        'full_features': full_features
    }
    t0 = datetime.now()
    res = coze_call(wf_id_name, params)
    log.info(f'/get_products_result coze_api: get_contents() costs {datetime.now() - t0}')
    log.info(f'__res: {res}')
    # products 中每一项有三个字段：content, score, product_num
    products_sorted = sorted(res['products'], key=lambda p: -p['score'])
    #
    # todo res 写到 db 里？
    #
    return ProductsResponse(products=products_sorted)
