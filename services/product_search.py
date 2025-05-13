import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))  # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

import uuid
from pydantic import BaseModel
import requests
from typing import List
from typing import Optional
import json
from data.search import SearchEntityExx
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
import aiohttp

class ProductSearchRequest(BaseModel):
    maxNum: Optional[int] = 5
    companyId: Optional[str] = ''
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

FLAG_NONE = 0
FLAG_USER_PREFERRED = 1
FLAG_BACK_FILLED = 2

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


# 正常流程：从 kb 召回，去 db 取 feature 并过滤
def retrieve_products_kb_db(task_id: str, max_num: int, my_company_id: str, recent_messages, user_input_summary: str, condition: dict):
    env = config['env']
    rerank_top_k = max_num * 8
    retries = 0
    t0 = datetime.now()
    dyna_res_0, prod_res_0 = {}, {}
    product_nums_bad = set() # 曾经被过滤掉的 product_num 们
    found = False
    while retries < 3:
        t1 = datetime.now()
        # step 1. 从 kb 召回 products，只用其 product_nums 列表
        kb_res = coze.search_product_kb(user_input_summary, rerank_top_k, env)
        t2 = datetime.now()
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} retrieve_kb costs {t2 - t1}')
        # kb_res 是 dict 类型
        product_nums_0 = set(kb_res['product_nums']) # 去重，因 kb 返回可能有重复的
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after retrieve_kb: {product_nums_0}')
        # 去掉曾经被过滤掉的
        product_nums_1 = product_nums_0 - product_nums_bad
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after filter_bad: {product_nums_1}')
        # step 2. 从 kb 取 product full features，并滤掉状态不正常的，并做 dynamic filtering
        dyna_res, prod_res = coze.get_full_features(product_nums_1, my_company_id, condition, env)
        dyna_res_0.update(dyna_res)
        prod_res_0.update(prod_res) # 把 dynamic filtering 的幸存者保存起来

        if len(dyna_res) > 0:
            product_nums_2 = dyna_res.keys()
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after filter_dynamic: {product_nums_2}')
            # step 5. filter by llm.check_products_matched
            t5 = datetime.now()
            model_name = config['model_product_matched']
            product_nums_3 = llm.check_products_matched(recent_messages, prod_res, task_id, model_name)
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} {model_name} filter_llm_matched costs {datetime.now() - t5}')
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} {model_name} after filter_llm_matched: {product_nums_3}')

            if len(product_nums_3) > 0:
                found = True
                break

        # 无人幸存。再试。
        rerank_top_k += max_num * 8
        product_nums_bad.update(product_nums_1)
        retries += 1

    log.info(f'/get_task_id {task_id} retrieve_products_kb_db total costs {datetime.now() - t0}')
    if found:
        product_nums_3 = list(product_nums_3)[:max_num]
        log.info(f'____prod_nums_3:{product_nums_3}')
        dyna_res_3 = {p: dyna_res[p] for p in dyna_res}
        prod_res_3 = {p: prod_res[p] for p in prod_res}
        return product_nums_3, prod_res_3, dyna_res_3, FLAG_NONE
    else:
        # 全军覆没。从曾经通过 dynamic filtering 但没通过 llm.if_matched 的中选两个
        # 如果这样也空，就不再努力了，返回空吧
        product_nums_3 = list(dyna_res_0.keys())[:2]
        log.info(f'looking for backfills: {product_nums_3}')
        dyna_res = {p: dyna_res_0[p] for p in dyna_res_0}
        prod_res = {p: prod_res_0[p] for p in prod_res_0}
        return product_nums_3, prod_res, dyna_res, FLAG_BACK_FILLED

# 从 db 召回用户指定的产品
def retrieve_products_db(task_id: str, product_nums: list):
    log.info(f'/get_task_id {task_id} retrieve_product_db product_nums:{product_nums}')
    if len(product_nums) == 0:
        return [], []
    env = config['env']
    t0 = datetime.now()
    # 调用时 my_company_id 和 condition 都为空，以达到「不过滤」的效果
    dyna_res, prod_res = coze.get_full_features(set(product_nums), '', {}, env)
    log.info(f'/get_task_id {task_id} db.get_dynamic_features costs {datetime.now() - t0}')
    return product_nums, prod_res, dyna_res

# 在单独的 thread 中运行，发射后不管
# 几乎都是 io 操作，故 thread 可以自行调度。
def retrieve_products_bg(task_id: str, request):
    log.info(f'/get_task_id {task_id} retrieve_products_bg() begins')
    tx = datetime.now()
    recent_messages = request.messages[-11:]
    condition, user_summary_intention = llm.analyze_user_input(recent_messages, task_id)
    log.info(f'/get_task_id {task_id} condition:{condition}')
    log.info(f'/get_task_id {task_id} user_summary_intention:{user_summary_intention}')

    user_input_summary = user_summary_intention['input_summary']
    user_intention = user_summary_intention['intention']

    if user_intention == 2: # 用户指定某些已推荐产品
        # 用户点名的，即使有不合适的，也不滤掉。不合适的原因应该会出现在 content 里
        # 但若 analyze_user_input 时识别 product_nums 出错，可能出现 product_num 不在 db 里的情况。
        #   这种需要滤掉（在 retrieve_products_db 时滤掉的）。此时只能请用户重新查询了。
        product_nums_preferred = user_summary_intention['product_nums']
        product_nums, prod_res, dyna_res = retrieve_products_db(task_id, product_nums_preferred)
        flag = FLAG_USER_PREFERRED
    else: # 1:用户希望推荐更多，或 0:其他
        product_nums, prod_res, dyna_res, flag = retrieve_products_kb_db(task_id, request.maxNum, request.companyId, recent_messages, user_input_summary, condition)

    log.info(f'/get_task_id {task_id} final product nums:{product_nums}')
    if len(product_nums) == 0:
        product_infos = []
    else:
        product_infos = [{
            'product_num' : pn,
            'product_feature' : prod_res[pn],#['product_feature'], # str
            # dynamic_feature 字段的格式为：dict {
            #     'product_num'          : str,
            #     'cals'                 : dict for machine,
            #     'product_feature'      : str for human
            #     'product_feature_dict' : dict for human
            # }
            'dynamic_feature' : dyna_res[pn],
            'full_feature' : prod_res[pn] + '\n' + dyna_res[pn]['product_feature'],
        } for pn in product_nums]

    flags = {
        'user_input_summary' : user_input_summary,
        'user_intention' : user_intention,
        'flag' : flag,
    }
    SearchEntityExx.create(
        task_id=task_id,
        max_num=request.maxNum,
        messages=json.dumps(request.messages, ensure_ascii=False, indent=4),
        user_input_summary=json.dumps(flags, ensure_ascii=False, indent=4),
        condition=json.dumps(condition, ensure_ascii=False, indent=4),
        user_intention='',
        product_infos=json.dumps(product_infos, ensure_ascii=False, indent=4)
    )
    log.info(f'/get_task_id {task_id} retrieve_products_bg() total costs {datetime.now() - tx}')

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


async def get_summary(task_id: str):
    log.info(f'/get_summary_result {task_id} get_summary() begins')
    start_time = datetime.now()
    timeout = timedelta(seconds=120)
    poll_interval = 0.5 # seconds

    data_ready = False
    while datetime.now() - start_time < timeout:
        # tt0 = datetime.now()
        search_entity = SearchEntityExx.query_first(task_id=task_id)
        #
        # 上面 tt0 和 下面 log 用于调试并发问题
        #
        # log.info(f'/get_summary_result {task_id} query_first costs {datetime.now() - tt0}')
        if search_entity:
            data_ready = True
            break
        await asyncio.sleep(poll_interval)

    waited = datetime.now() - start_time
    if not data_ready: # 超时：前面 get_task_id 出错了
        log.info(f'/get_summary_result {task_id} timeout costs {waited}. return.')
        yield 'data: 不好意思，似乎出了些问题，目前没有可以推荐的\n\n'
        return

    log.info(f'/get_summary_result {task_id} data ready costs {waited}')

    # 从 db 里取出的 user_summary 为空字符串：前面 get_task_id 出错了
    if search_entity.user_input_summary == '':
        log.info(f'/get_summary_result {task_id} db.user_input_summary empty. return.')
        yield 'data: 不好意思，似乎出了些问题，目前没有可以推荐的\n\n'
        return

    recent_messages = json.loads(search_entity.messages)[-11:]
    # user_input_summary = search_entity.user_input_summary
    product_infos = json.loads(search_entity.product_infos)
    # log.info(f'__user_input_summary: {user_input_summary}')
    # log.info(f'__product_infos: {product_infos}')
    if len(product_infos) == 0:
        # get_task_id 时，没查到合适的产品。直接返回。
        # request.product_infos 是空 json 对象序列化成的字符串，其值为 '[]'。
        # product_infos 则为空 list。用它判断比较方便。
        # 这里若不返回，后续 full_features 拼接出来为空串。
        # 再用该空 full_features 以及正常的 user_input_summary 通过 llm 生成 summary，
        # llm 会产生幻觉，捏造出不存在的 product num。
        log.info(f'/get_summary_result {task_id} db.product_infos empty. return.')
        yield 'data: 不好意思，没有查到合适的产品。您可以换个描述再试试。\n\n'
        return

    # todo: 原版计算 summary 时，各产品是按 score 从高到低排序的，
    #       意味着计算 summary 要在 content/score 都算出来之后
    #       现在先不管这个

    full_features = '\n\n'.join([p['full_feature'] for p in product_infos])
    flag = json.loads(search_entity.user_input_summary)['flag']
    if flag == FLAG_USER_PREFERRED:
        tip_str = '这些产品是以前推荐过、顾客觉得比较好的。'
    elif flag == FLAG_BACK_FILLED:
        tip_str = '这些产品是在没找到合适产品的情况下，用来兜底的。'
    else:
        tip_str = ''
    log.info(f'__get_summary flag:{flag}, tip_str:{tip_str}')

    prompt = f'''
#要求#
根据顾客与旅游行业客服人员的对话内容，总结出顾客的旅行需求。然后从给定的各产品信息中，向顾客推荐最合适的几个。
不要超过五百字。回答文字要平实，不要带文学色彩。要简短，不要啰嗦。

#限制#
1. 忽略顾客可能提到的对推荐数量的要求（类似“给我推荐10个产品”这样的）。一个产品最多推荐一次，不要把一个产品以
   多个团期的方式推荐多次。即使最后推荐数量达不到顾客的数量要求也没关系。
2. productNum 是产品的唯一标识，标题是产品的重要特征。必须包含每个产品的 productNum 和标题。
3. 只要提及产品，无论之前是否出现过，都要重新给出产品的 productNum。
4. 但不要出现 "productNum" 这个英文词，要用“编号为某某的产品”这样的方式。
5. {tip_str}即使某产品不太符合顾客需求，也不要直接说它不合适，而是要用类似“虽然它不完全匹配，但也比较相关”这样的话术。

#产品信息#
======
{full_features}
======

#顾客与客服人员的对话内容#
======
{recent_messages}
======
'''

    messages = [
        {
            'role': 'user',
            'content': prompt
        }
    ]
    model_name = config['model_summary']
    log.info(f'/get_summary_result {task_id} before calling {model_name}')
    cnt = 0
    t0 = datetime.now()
    t1 = t0 # 万一没有第一个 chunk，给 t1 设个初值
    async for item in llm.stream_generate_ex(messages, task_id, 'get_summary', model_name):
        cnt += 1
        if cnt == 1:
            t1 = datetime.now()
            log.info(f'/get_summary_result {task_id} {model_name} first chunk arrived. costs first {t1 - t0}, wait+first {t1 - start_time}')
        # log.info(f'/get_summary_result chunk {cnt-1} _{item.strip()}_')
        yield item
    t2 = datetime.now()
    log.info(f'/get_summary_result {task_id} {model_name} all chunks arrived. cost all {t2 - t1}, wait+first+all {t2 - start_time}')

async def get_products(task_id: str, timeout_secs: int):
    log.info(f'/get_products_result {task_id} get_products() begins')
    start_time = datetime.now()
    timeout = timedelta(seconds=timeout_secs)
    poll_interval = 0.2 # seconds

    data_ready = False
    while datetime.now() - start_time < timeout:
        # tt0 = datetime.now()
        search_entity = SearchEntityExx.query_first(task_id=task_id)
        #
        # 上面 tt0 和 下面 log 用于调试并发问题
        #
        # log.info(f'/get_products_result {task_id} query_first costs {datetime.now() - tt0}')
        if search_entity:
            data_ready = True
            break
        await asyncio.sleep(poll_interval)

    waited = datetime.now() - start_time
    if not data_ready:
        log.info(f'/get_products_result {task_id} timeout costs {waited}')
        return ProductsResponse(products=[])
    log.info(f'/get_products_result {task_id} data ready costs {waited}')

    # 从 db 里取出的 products 为空字符串：前面 get_task_id 出错了
    if search_entity.product_infos == '':
        log.info(f'/get_products_result {task_id} db.product_infos empty')
        return ProductsResponse(products=[])

    prod_infos = json.loads(search_entity.product_infos)
    recent_messages = json.loads(search_entity.messages)[-11:]

    t0 = datetime.now()
    model_name = config['model_content']
    res_contents = llm.get_product_contents(recent_messages, prod_infos, task_id, model_name)
    log.info(f'/get_products_result {task_id} {model_name} llm.get_contents costs {datetime.now() - t0}')
    log.info(f'/get_products_result {task_id} {model_name} llm.get_contents result {res_contents}')
    # log.info(f'_______________ res_contents from llm {model_name}, before sorting _{res_contents}')
    # res_contents 中每一项有三个字段：content, score, product_num
    products_sorted = sorted(res_contents, key=lambda p: -p['score'])
    log.info(f'/get_products_result {task_id} get_contents costs {datetime.now() - t0}')
    log.info(f'/get_products_result {task_id} get_contents result {products_sorted}')

    return ProductsResponse(products=products_sorted)


if __name__ == '__main__':
    task_id = 'mock_task_id_1234'
    msg = [
        {
            "role": "user",
            "content": "您好，想去新加坡和马来西亚，大概一周时间，父母二人带一个十二岁男孩。有什么推荐吗？"
        },
    ]
    retrieve_products_bg(task_id, ProductSearchRequest(messages=msg))
