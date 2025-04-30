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
from concurrent.futures import ThreadPoolExecutor

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


'''
def user_input_summary_condition(task_id: str, request_messages):
    env = config['env']
    wf_id_name = 'coze_product_search_task_wf_id'
    params = {
        'env': env,
        'messages': request_messages
    }
    log.info(f'/get_task_id {task_id} wf.analyze_user_input before coze_call_sync')
    t0 = datetime.now()
    # 不是 async 函数（因要用在 thread 中），无法 await 其 async 版本，只能用 sync 版本
    res = coze_workflow_sync(wf_id_name, params)
    log.info(f'/get_task_id {task_id} wf.analyze_user_input costs {datetime.now() - t0}')
    return res

def analyze_user_input_complete(task_id: str, request_messages):
    log.info(f'/get_task_id {task_id} analyze_user_input before launch')
    t0 = datetime.now()
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(user_input_summary_condition, task_id, request_messages)
        model_name = 'qwen-turbo'
        f2 = executor.submit(llm.analyze_user_input, request_messages, task_id, model_name)
    res = f1.result()
    res2 = f2.result()
    log.info(f'/get_task_id {task_id} analyze_user_input costs {datetime.now() - t0}')

    # qwen 调用，与 coze workflow 对比。目前保留 coze 方式。
    # t00 = datetime.now()
    # model_name = 'qwen-plus'
    # user_analysis_qwen = llm.analyze_user_input(request.messages, task_id, model_name)
    # log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
    # log.info(f'/get_task_id {task_id} {model_name}.user_input_summary:{user_analysis_qwen[0]}')
    # log.info(f'/get_task_id {task_id} {model_name}.condition:{user_analysis_qwen[1]}')
    return (res, res2)
'''


'''
def retrieve_products_kb_db_orig(task_id: str, max_num: int, recent_messages, user_input_summary: str, condition):
    env = config['env']
    rerank_top_k = max_num
    retries = 0
    t0 = datetime.now()
    while retries < 3:
        t1 = datetime.now()
        kb_res = coze.search_product_kb(user_input_summary, rerank_top_k, env)
        t2 = datetime.now()
        log.info(f'/get_task_id {task_id} kb.retrieve costs {t2 - t1}')
        # kb_res 是 dict 类型
        product_nums = kb_res['product_nums']
        log.info(f'/get_task_id {task_id} kb.retrieve result:{product_nums}')
        dyna_res = coze.get_dynamic_features(product_nums, env)
        t3 = datetime.now()
        log.info(f'/get_task_id {task_id} db.get_dynamic_features costs {t3 - t2}')
        remaining_product_nums = coze.filter_dynamic(condition, dyna_res)['product_nums']
        if len(remaining_product_nums) > 0:
            break
        rerank_top_k += max_num
        retries += 1
    t4 = datetime.now()
    log.info(f'/get_task_id {task_id} co.retrieve_kb_dynamic_features total costs {t4 - t0}')

    log.info(f'__remaining_product_nums:{remaining_product_nums}')
    t0 = datetime.now()
    prod_res = coze.get_product_features(remaining_product_nums, env)
    log.info(f'/get_task_id {task_id} db.get_product_features costs {datetime.now() - t0}')
    return remaining_product_nums, prod_res, dyna_res
'''

def retrieve_products_kb_db(task_id: str, max_num: int, recent_messages, user_input_summary: str, condition):
    env = config['env']
    rerank_top_k = max_num * 2
    retries = 0
    t0 = datetime.now()
    product_nums_bad = set() # 曾经被过滤掉的 product_num 们
    found = False
    while retries < 3:
        t1 = datetime.now()
        # step 1. 从 kb 召回 products，只用其 product_nums 列表
        kb_res = coze.search_product_kb(user_input_summary, rerank_top_k, env)
        t2 = datetime.now()
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} retrieve_kb costs {t2 - t1}')
        # kb_res 是 dict 类型
        product_nums_0 = list(set(kb_res['product_nums'])) # 去重，因 kb 返回可能有重复的
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after retrieve_kb: {product_nums_0}')
        # 去掉曾经被过滤掉的
        product_nums_1 = list(set(product_nums_0) - product_nums_bad)
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after filter_bad: {product_nums_1}')
        # step 2. 从 kb 取 dynamic features
        dyna_res = coze.get_dynamic_features(product_nums_1, env)
        log.info(f'________dynamic features:{dyna_res}')
        t3 = datetime.now()
        log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} db.get_dynamic_features costs {t3 - t2}')
        # step 3. filter by dynamic 暂时不用 dynamic filter
        # product_nums_2 = coze.filter_dynamic(condition, dyna_res)['product_nums']
        # log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} after filter_dynamic: {product_nums_2}')
        product_nums_2 = product_nums_1
        if len(product_nums_2) > 0:
            # step 4. 从 db 取 product features，用于 content 过滤
            t4 = datetime.now()
            prod_res = coze.get_product_features(product_nums_2, env)
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} db.get_product_features costs {datetime.now() - t4}')
            log.info(f'________product features:{prod_res}')
            # todo 有时 get_product_features() 的返回值里不含某个产品，导致下一句出错
            prod_diff_tmp = {pn for pn in dyna_res} - {pn for pn in prod_res}
            log.info(f'________product difffffffff: {prod_diff_tmp}')

            # step 5. filter by llm_check_products_matched
            # full_features = [
            #     (pn, prod_res[pn]['product_feature'] + '\n' + dyna_res[pn]['product_feature'], dyna_res[pn]['cals'])
            #     for pn in product_nums_2 if pn in prod_res and pn in dyna_res
            # ]

            # step 5. 新方法：dynamic 为 dict
            full_features = [
                (pn, prod_res[pn]['product_feature'], dyna_res[pn]['product_feature_dict'])
                for pn in product_nums_2 if pn in prod_res and pn in dyna_res
            ]
            log.info(f'________________full_features:{full_features}')
            t5 = datetime.now()
            model_name = config['model_product_matched']
            product_nums_3 = llm.check_products_matched(recent_messages, full_features, task_id, model_name)
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} {model_name} filter_llm_matched costs {datetime.now() - t5}')
            log.info(f'/get_task_id {task_id} retrieve_products_kb_db retry:{retries} {model_name} after filter_llm_matched: {product_nums_3}')

            if len(product_nums_3) > 0:
                found = True
                break

        # 无人幸存。再试。
        rerank_top_k += max_num
        product_nums_bad.update(set(product_nums_1))
        retries += 1

    log.info(f'/get_task_id {task_id} retrieve_products_kb_db total costs {datetime.now() - t0}')
    if found:
        product_nums_3 = product_nums_3[:max_num]
        log.info(f'______prod_nums_3:{product_nums_3}')
        # prod_res_3 = [prod_res[pn] for pn in product_nums_3]
        # dyna_res_3 = [dyna_res[pn] for pn in product_nums_3]
        return product_nums_3, prod_res, dyna_res
    else:
        # 全军覆没。从最后一轮从 kb 里取出的里面选 2 个。
        product_nums_3 = product_nums_0[:2]
        dyna_res = coze.get_dynamic_features(product_nums_1, env)
        for i in dyna_res:
            i['cals']['back_filled'] = True
        prod_res = coze.get_product_features(product_nums_2, env)
        # to do: 可能没有
        return product_nums_3, prod_res, dyna_res

def retrieve_products_db(task_id: str, product_nums: list):
    log.info(f'/get_task_id {task_id} retrieve_product_db product_nums:{product_nums}')
    if len(product_nums) == 0:
        return [], []
    env = config['env']
    t0 = datetime.now()
    dyna_res = coze.get_dynamic_features(product_nums, env)
    for i in dyna_res:
        i['cals']['user_preferred'] = True
    log.info(f'/get_task_id {task_id} db.get_dynamic_features costs {datetime.now() - t0}')

    # 过滤掉不在 db 里（也就是，不在返回的 dyna_res 里）的 product_num
    product_nums = list(dyna_res.keys())
    log.info(f'/get_task_id {task_id} retrieve_products_db final_product_nums:{product_nums}')

    t0 = datetime.now()
    prod_res = coze.get_product_features(product_nums, env)
    log.info(f'/get_task_id {task_id} db.get_product_features costs {datetime.now() - t0}')
    return product_nums, prod_res, dyna_res

# 在单独的 thread 中运行，发射后不管
# 几乎都是 io 操作，故 thread 可以自行调度。
def retrieve_products_bg(task_id: str, request):
    log.info(f'/get_task_id {task_id} retrieve_products_bg() begins')
    tx = datetime.now()
    recent_messages = request.messages[-11:]
    condition, user_summary_intention = llm.analyze_user_input(recent_messages, task_id, config['model_user_summary_intention'])
    log.info(f'/get_task_id {task_id} condition:{condition}')
    log.info(f'/get_task_id {task_id} user_summary_intention:{user_summary_intention}')

    user_input_summary = user_summary_intention['input_summary']
    user_intention = user_summary_intention['intention']

    if user_intention == 2: # 用户指定某些已推荐产品
        # 用户点名的，即使有不合适的，也不滤掉。不合适的原因应该会出现在 content 里
        # 但若 analyze_user_input 时识别 product_nums 出错，可能出现 product_num 不在 db 里的情况。
        #   这种需要滤掉（在 retrieve_products_db 时滤掉的）。此时只能请用户重新查询了。
        # todo: 万一全被滤掉，得滥竽一下
        product_nums_preferred = user_summary_intention['product_nums']
        product_nums, prod_res, dyna_res = retrieve_products_db(task_id, product_nums_preferred)
    else: # 1:用户希望推荐更多，或 0:其他
        product_nums, prod_res, dyna_res = retrieve_products_kb_db(task_id, request.maxNum, recent_messages, user_input_summary, condition)


    log.info(f'/get_task_id {task_id} final product nums:{product_nums}')
    if len(product_nums) == 0:
        product_infos = []
    else:
        product_infos = [{
            'product_num' : pn,
            'product_feature' : prod_res[pn]['product_feature'],
            'dynamic_feature' : dyna_res[pn]['product_feature'],
            'full_feature' : prod_res[pn]['product_feature'] + '\n' + dyna_res[pn]['product_feature'],
            'cals' : dyna_res[pn]['cals'],
        } for pn in product_nums]
        log.info(f'__product_infos: {product_infos}')

    SearchEntityExx.create(
        task_id=task_id,
        max_num=request.maxNum,
        messages=json.dumps(request.messages, ensure_ascii=False, indent=4),
        user_input_summary=user_input_summary,
        condition=json.dumps(condition, ensure_ascii=False, indent=4),
        user_intention=user_intention,
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

    full_features = "\n\n".join([p['product_feature'] + '\n' + p['dynamic_feature'] for p in product_infos])

    #
    # todo 优化这个 prompt
    # todo 没有用到 cals 中的 user_preferred 和 lanyu 属性，也没判断产品是否没有动态特征
    #
    prompt = f'''
根据用户的对话历史，总结出用户的旅行需求。然后根据各产品信息，向用户推荐最合适的若干个产品。
不要超过五百字。回答文字要平实，不要带文学色彩。要简短，不要啰嗦。

### 限制
1. productNum 是产品的唯一标识，标题是产品的重要特征。必须包含每个产品的 productNum 和标题。
2. 只要提及产品，无论之前是否出现过，都要重新给出产品的 productNum。
3. 但不要出现 "productNum" 这个英文词，要用"编号为某某的产品"这样的方式。
4. 即使某产品不太符合用户需求，也不要直接说它不合适，而是要用类似"虽然它不完全匹配，但也比较相关"这样的话术。

### 产品信息：

{full_features}

### 用户对话历史：

{recent_messages}
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

    ##### for now, disables qwen-plus, uses qwen-turbo instead
    # model_name = 'qwen-plus'
    # log.info(f'/get_summary_result {task_id} before calling {model_name}')
    # cnt = 0
    # t0 = datetime.now()
    # t1 = t0 # 万一没有第一个 chunk，给 t1 设个初值
    # buffer = ''
    # async for item in llm.stream_generate_ex(messages, task_id, 'get_summary', model_name):
    #     cnt += 1
    #     if cnt == 1:
    #         t1 = datetime.now()
    #         log.info(f'/get_summary_result {task_id} {model_name} first chunk arrived. costs first {t1 - t0}, wait+first {t1 - start_time}')
    #     # log.info(f'/get_summary_result {task_id} chunk {cnt}')
    #     # yield item
    #     buffer += item.strip()[len('data: '):]
    # t2 = datetime.now()
    # log.info(f'/get_summary_result {task_id} {model_name} all chunks arrived. cost all {t2 - t1}, wait+first+all {t2 - start_time}')
    # log.info(f'/get_summary_result {task_id} {model_name} summary: {buffer}')

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
    log.info(f'_______________ res_contents from llm {model_name}, before sorting _{res_contents}')
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
        # {
        #     "role": "assistant",
        #     "content": "为你推荐编号为 U174845 的产品，【众信制造：金牌南洋传奇】新加坡+马来西亚北京起止 5 晚 7 天。该产品的线路特色包括双峰塔-国家皇宫-广场-国家艺术馆-CITYWALK 城市单轨车-彩虹阶梯-阿罗街。此外，该产品还包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、新加坡。\n\n或者你也可以考虑编号为 U167657 的产品，北京起止【寻味南洋-米其林之旅】新加坡+马来西亚 7 天。该产品有两条线路可供选择，线路 A 是马进新出 CA871，线路 C 是大兴去首都回。产品特色是寻味南洋-米其林之旅，你可以品尝到当地的美食。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、马来西亚和亚洲、新加坡。\n\n如果你从河南郑州出发，还可以选择编号为 U179033 的产品，【新加坡乐园 MAX】郑州起止 4 晚 6 天。该产品升级 2 晚国际四星，包含新加坡环球影城+飞禽动物园+日间动物园三大乐园精彩之行。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、中文导游服务、境外旅游人身意外险、行程所含景点（区）门票等。出发地为河南郑州，目的地为亚洲、新加坡。"
        # },
        # {
        #     "role": "user",
        #     "content": "这几个都不错，帮我比较一下它们的特色吧，排个序",
        #     # "content": "嗯，我们不希望太累，想轻松点。从北京出发。费用不是问题，至少五万起。要快，本周末之前必须出发。"
        # }
    ]

    msg = [
        {
            "role": "user",
            "content": "想五一期间去澳大利亚和新西兰转转，别太累，别自驾"
        },
    ]
    retrieve_products_bg(task_id, ProductSearchRequest(messages=msg))
