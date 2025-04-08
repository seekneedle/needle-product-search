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

async def coze_workflow_async(wf_id, params):
    url = config['coze_api_url']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': decrypt(config['coze_api_auth'])
    }
    data = {
        "workflow_id": config[wf_id],
        "parameters": params
    }
    log.info(f'coze_call_async params: wf:{wf_id} {params}')
    # response = requests.post(url, headers=headers, json=data)

    # coze workflow 返回格式：https://www.coze.cn/open/docs/developer_guides/workflow_run
    retries = 0
    while retries < 3:
        log.info(f'coze_call_async wf:{wf_id} retries:{retries} before aiohttp.post')
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                log.info(f'coze_call_async wf:{wf_id} retries:{retries} after aiohttp.post')
                if response.status == 200:
                    response_data = await response.json()
                    log.info(f'coze_call_async wf:{wf_id} retries:{retries} http ok, response:{response_data}')
                    if response_data['code'] == 0: # coze workflow 执行成功
                        input_data = response_data['data']
                        try:
                            parsed_data = json.loads(input_data)
                            return parsed_data
                        except json.JSONDecodeError:
                            err = f'coze_call_async wf:{wf_id} retries:{retries} json parse error:{response.status}, 响应内容: {await response.text()}'
                            log.error(err)
                            # raise RequestError(response.status, err)
                    else: # coze workflow 执行失败
                        pass # 不需要干啥（log 也在上面打了），retry 下一次
                else:
                    err = f'coze_call_async wf:{wf_id} retries:{retries} http bad {response.status}, 响应内容: {await response.text()}'
                    log.error(err)
                    # raise RequestError(response.status, err)
        await asyncio.sleep(1)
        retries += 1
    return None

def coze_workflow_sync(wf_id, params):
    return asyncio.run(coze_workflow_async(wf_id, params))

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


# 在单独的 thread 中运行，发射后不管
# 依次做如下操作：
#   计算 user_input_summary 和 conditions。coze workflow。(io: network)
#   从 kb 召回产品。(io: network)
#   从 client db，get_dynamic_features (io: network)
#   filter_dynamic (cpu)
#   从 client db，get_product_features (io: network)
#   写入 local sqlite (io: disk)
# 几乎都是 io 操作，故 thread 可以自行调度。

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

def retrieve_product_kb_db(task_id: str, max_num: int, user_input_summary: str, condition):
    env = config['env']
    rerank_top_k = max_num
    retries = 0
    t0 = datetime.now()
    while retries < 3:
        t1 = datetime.now()
        kb_res = coze.search_product_kb(user_input_summary, rerank_top_k, env)
        t2 = datetime.now()
        log.info(f'/get_task_id {task_id} kb.retrieve costs {t2 - t1}')
        #
        # todo better logging for kb_res
        # kb_product_nums = kb_res['product_nums'] if kb_res is not None and
        log.info(f'/get_task_id {task_id} kb.retrieve result:{kb_res}')
        product_nums = kb_res['product_nums']
        dyna_res = coze.get_dynamic_features(product_nums, env)['products']
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
    prod_res = coze.get_product_features(remaining_product_nums, env)['products']
    log.info(f'/get_task_id {task_id} db.get_product_features costs {datetime.now() - t0}')
    return (remaining_product_nums, prod_res, dyna_res)

def retrieve_product_db(task_id: str, product_nums: list):
    log.info(f'/get_task_id {task_id} retrieve_product_db product_nums:{product_nums}')
    if len(product_nums) == 0:
        return ([], [])
    env = config['env']
    t0 = datetime.now()
    dyna_res = coze.get_dynamic_features(product_nums, env)['products']
    log.info(f'/get_task_id {task_id} db.get_dynamic_features costs {datetime.now() - t0}')

    # 过滤掉不在 db 里（也就是，不在返回的 dyna_res 里）的 product_num
    product_nums = list(dyna_res.keys())
    log.info(f'/get_task_id {task_id} retrieve_product_db final_product_nums:{product_nums}')

    t0 = datetime.now()
    prod_res = coze.get_product_features(product_nums, env)['products']
    log.info(f'/get_task_id {task_id} db.get_product_features costs {datetime.now() - t0}')
    return (product_nums, prod_res, dyna_res)

def retrieve_products_bg(task_id: str, request):
    log.info(f'/get_task_id {task_id} retrieve_products_bg() begins')
    tx = datetime.now()
    res, res2 = analyze_user_input_complete(task_id, request.messages)
    # 若 workflow.analyze_user_input 返回为 None，说明有内部错误，目前无法处理。
    # 将 user_input_summary, condition, product_infos 都置为空，写入 db，供后续两个调用使用。
    if res is None:
        log.info(f'/get_task_id {task_id} wf.analyze_user_input result None')
        SearchEntityExx.create(
            task_id=task_id,
            max_num=0,
            messages=json.dumps(request.messages, ensure_ascii=False, indent=4),
            user_input_summary='',
            condition='',
            user_intention=0,
            product_infos=''
        )
        log.info(f'/get_task_id {task_id} retrieve_products_bg() total costs {datetime.now() - tx}')
        return

    user_input_summary = res['user_input_summary']
    condition = res['condition']
    user_intention = res2[0]['intention']
    log.info(f'/get_task_id {task_id} user_input_summary:{user_input_summary}')
    log.info(f'/get_task_id {task_id} condition:{condition}')
    log.info(f'/get_task_id {task_id} user_intention:{res2[0]}')

    if user_intention == 2: # 用户指定某些已推荐产品
        # 用户点名的，即使有不合适的，也不滤掉。不合适的原因应该会出现在 content 里
        # 若 analyze_user_input 时识别 product_nums 出错，可能出现 product_num 不在 db 里的情况。
        #   这种需要滤掉（在 retrieve_product_db 时滤掉的）
        product_nums = res2[0]['product_nums']
        product_nums, prod_res, dyna_res = retrieve_product_db(task_id, product_nums)
        # log.info(f'_____________prod_res type:{type(prod_res)}, _|{prod_res}|_')
        # log.info(f'_____________dyna_res type:{type(dyna_res)}, _|{dyna_res}|_')
    else: # 1:用户希望推荐更多，或 0:其他
        product_nums, prod_res, dyna_res = retrieve_product_kb_db(task_id, request.maxNum, user_input_summary, condition)

    log.info(f'/get_task_id {task_id} final product nums:{product_nums}')
    product_infos = [{
        'product_num' : pn,
        'product_feature' : prod_res[pn]['product_feature'],
        'dynamic_feature' : dyna_res[pn]['product_feature'],
        'cals' : dyna_res[pn]['cals']
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

async def get_summary(task_id: str):
    log.info(f'/get_summary_result {task_id} get_summary() begins')
    start_time = datetime.now()
    timeout = timedelta(seconds=60)
    poll_interval = 0.2 # seconds

    data_ready = False
    while datetime.now() - start_time < timeout:
        # tt0 = datetime.now()
        request = SearchEntityExx.query_first(task_id=task_id)
        #
        # 上面 tt0 和 下面 log 用于调试并发问题
        #
        # log.info(f'/get_summary_result {task_id} query_first costs {datetime.now() - tt0}')
        if request:
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
    if request.user_input_summary == '':
        log.info(f'/get_summary_result {task_id} db.user_input_summary empty. return.')
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
    #
    prompt = f'''
根据产品信息，简短回答客户问题，不要超过五百字。回答文字要平实，不要带文学色彩。要简短，不要啰嗦。

### 限制
1. productNum 是产品的唯一标识，必须包含每个产品的 productNum。
2. 只要提及产品，无论之前是否出现过，都要重新给出产品的 productNum。
3. 但不要出现 "productNum" 这个英文词，要用"编号为某某的产品"这样的方式。

### 产品信息：

{full_features}

### 用户的需求：

{user_input_summary}
'''

    messages = [
        {
            'role': 'user',
            'content': prompt
        }
    ]
    model_name = 'qwen-turbo'
    log.info(f'/get_summary_result {task_id} before calling {model_name}')
    cnt = 0
    t0 = datetime.now()
    t1 = t0 # 万一没有第一个 chunk，给 t1 设个初值
    async for item in llm.stream_generate_ex(messages, task_id, 'get_summary', model_name):
        cnt += 1
        if cnt == 1:
            t1 = datetime.now()
            log.info(f'/get_summary_result {task_id} {model_name} first chunk arrived. costs first {t1 - t0}, wait+first {t1 - start_time}')
        # log.info(f'/get_summary_result {task_id} chunk {cnt}')
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

    #
    # todo: res 写到 db 里？
    #

async def get_products(task_id: str, timeout_secs: int):
    log.info(f'/get_products_result {task_id} get_products() begins')
    start_time = datetime.now()
    timeout = timedelta(seconds=timeout_secs)
    poll_interval = 0.2 # seconds

    data_ready = False
    while datetime.now() - start_time < timeout:
        # tt0 = datetime.now()
        products_entity = SearchEntityExx.query_first(task_id=task_id)
        #
        # 上面 tt0 和 下面 log 用于调试并发问题
        #
        # log.info(f'/get_products_result {task_id} query_first costs {datetime.now() - tt0}')
        if products_entity:
            data_ready = True
            break
        await asyncio.sleep(poll_interval)

    waited = datetime.now() - start_time
    if not data_ready:
        log.info(f'/get_products_result {task_id} timeout costs {waited}')
        return ProductsResponse(products=[])
    log.info(f'/get_products_result {task_id} data ready costs {waited}')

    # 从 db 里取出的 products 为空字符串：前面 get_task_id 出错了
    if products_entity.product_infos == '':
        log.info(f'/get_products_result {task_id} db.product_infos empty')
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
    log.info(f'/get_products_result {task_id} before wf.get_contents')
    res = await coze_workflow_async(wf_id_name, params)
    if res is None:
        return ProductsResponse(products=[])

    log.info(f'/get_products_result {task_id} wf.get_contents costs {datetime.now() - t0}')
    log.info(f'/get_products_result {task_id} wf.get_contents result {res}')
    # products 中每一项有三个字段：content, score, product_num
    products_sorted = sorted(res['products'], key=lambda p: -p['score'])
    #
    # todo res 写到 db 里？
    #
    return ProductsResponse(products=products_sorted)
