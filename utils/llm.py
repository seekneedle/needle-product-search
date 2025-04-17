import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent)) # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

from openai import OpenAI, APIError
from utils.security import decrypt
from utils.config import config
from utils.log import log
import multiprocessing
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import traceback

client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

def qwen_call(messages, return_type: str, task_id: str, job_name: str, model_name: str):
    # task_id 和 job_name 只用于 logging 目的
    log.info(f'{task_id} {model_name} {job_name} begins')
    t0 = datetime.now()
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={'type': return_type}
        )
        log.info(f'{task_id} {model_name} {job_name} done, cost {datetime.now() - t0}')
        return completion.choices[0].message.content
    except APIError as e:
        log.info(f'{task_id} {model_name} {job_name} APIError: {e.status_code}, {e.code}, {e.message}')
        return ''
    except Exception as e:  # 其他异常（如网络问题）
        log.info(f'{task_id} {model_name} {job_name} api Exception: {str(e)}')
        return ''

# 无 log 的版本。（带大量 log 的版本，见本文件下方）
def qwen_stream_call(messages, queue, model_name: str):
    # task_id 和 job_name 只用于 logging 目的
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,
        stream_options={'include_usage': False} # 不需要得到 token 使用情况统计
    ) # 貌似是第一个 chunk 返回时才返回
    for chunk in completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content is not None: # 真正的回复
            queue.put(f'data: {delta.content}\n\n')
    queue.put(None)

# wrapper for qwen_stream_call()
async def stream_generate_ex(messages, task_id: str, job_name: str, model_name: str):
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER before calling qwen')
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=qwen_stream_call, args=(messages, queue, model_name))
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER before process.start()')
    process.start()
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER after process.start()')

    try:
        cnt = 0
        while True:
            # 异步监听队列（避免阻塞事件循环）
            data = await asyncio.get_event_loop().run_in_executor(
                None,  # 使用默认线程池
                queue.get  # 阻塞调用，但通过线程池转为异步
            )
            if cnt == 0:
                log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER first chunk received')
            cnt += 1
            if data is None: # 结束信号
                break
            yield data  # 返回 SSE 数据
    finally:
        process.join()  # 确保进程退出


'''
# original by huaxing. not used.
async def stream_generate(messages):
    completion = client.chat.completions.create(
        model='qwen-plus-2024-09-19',
        messages=messages,
        stream=True,
        stream_options={'include_usage': True}
    )
    for chunk in completion:
        if len(chunk.choices) > 0:
            yield f'data: {chunk.choices[0].delta.content}\n\n'

# log 很多的版本，暂存一阵
def qwen_stream_call_logs(messages, queue):
    log.info('__qwen_stream_call get_summary REALLY before calling qwen')
    t0 = datetime.now()
    completion = client.chat.completions.create(
        # model='qwen-plus-2024-09-19',
        # model='qwq-plus',
        model='qwen-plus',
        # model='qwen-turbo',
        messages=messages,
        stream=True, # QwQ 模型仅支持流式输出方式调用
        stream_options={'include_usage': False} # 不需要得到 token 使用情况统计
    ) # 貌似是第一个 chunk 返回时才返回
    log.info('__qwen_stream_call get_summary REALLY after calling qwen')
    # first_arrived = False
    # first_reason_arrived = False
    first_content_arrived = False
    for chunk in completion:
        # if not first_arrived:
        #     first_arrived = True
        #     log.info(f'__qwen_stream_call get_summary REALLY chunk: first costs {datetime.now() - t0}')
        if not chunk.choices:
            # log.info(f'__qwen_stream_call get_summary usage:{chunk.usage}')
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
            # 思考过程。qwq 有，qwen-* 无。此时 delta.content 值为 None。
            pass
            # if not first_reason_arrived:
            #     first_reason_arrived = True
            #     log.info(f'__qwen_stream_call get_summary REALLY chunk: first reason costs {datetime.now() - t0}')
        else:
            # 真正的回复
            if not first_content_arrived:
                first_content_arrived = True
                log.info(f'__qwen_stream_call get_summary REALLY chunk: first content costs {datetime.now() - t0}')
            queue.put(f'data: {delta.content}\n\n')
    queue.put(None)
'''

#
# 目前只用到了 user_intention
#
def analyze_user_input(recent_messages: list, task_id: str, model_name: str):
    # prompt_user_input = f'''
    #     根据用户聊天历史，总结用户对旅行产品的需求。要以用户的口吻输出，不要以客服人员的角度总结。
    #     如果总结中涉及到已推荐产品，要带上产品编号，但不要带其标题。
    #     如果不涉及已推荐产品，就不用说"目前没有提到具体推荐的产品编号"这样的话。
    #     输出文字要平实，不要带文学色彩。要简短，不要啰嗦。
    #     用户聊天历史记录为：{recent_messages}
    # '''

    prompt_condition = f'''
        ### 角色
        根据客户user的聊天历史，总结客户对于出行时间、产品价格、产品存量的需求，放到 json 对象中，结构化返回。

        注意，提取各种时间时，

        ### 能力1：提取产品出行时间要求
        1. 根据聊天历史，提取客户希望的出发时间到 depart_date，如果没有提及出发时间，则输出空。
        2. 根据聊天历史，提取客户希望的返回时间到 back_date，如果没有提及返回时间，则输出空。
        3. 提取格式为 yyyy-MM-dd，比如：2025-06-29。
        4. 如果用户提到的日期没说是哪年，则认为是今年。若没说是几月，则认为是这个月。

        ### 能力2：提取产品的时长
        1. 根据聊天历史，提取客户要求的最少旅游多少天，放到 min_days。若未提及，则输出 0
        2. 根据聊天历史，提取客户要求的最多旅游多少天。放到 max_days。若未提及，则输出 0

        ### 能力3：提取产品存量要求
        1. 根据聊天历史，提取客户要求的最少存量，放入 stock 里。存量不能小于 1。
        2. 如果用户没有提及最小存量，默认为 1。
        3. 输出存量必须是整数。

        ### 能力4：提取产品价格要求
        1. 根据聊天历史，提取客户要求的最低价格，放到 min_price 里。若未提及最低价格，则最低价格输出 0。
        2. 根据聊天历史，提取客户要求的最高价格，放到 max_price 里。若未提及最高价格，则最高价格输出 0。

        ### 限制
        1. 不允许编造内容。
        2. 必须严格按客户聊天历史中的信息进行提取。

        ### 用户聊天历史

        {recent_messages}
    '''

    # prompt_user_intention = f'''
    #     根据用户聊天历史，判断用户最后的意图。结果放到 json 对象中，结构化返回。
    #     如果用户感觉以前系统推荐的产品不太合适、或者不够多，希望再推荐些其他产品，返回 intention = 1。
    #     如果用户表示出对某个或某几个产品的肯定，或进一步询问已推荐的一个或几个产品的详细信息（如出发日期、价格、特点等），或想对比几个已推荐产品的某些特点，返回 intention = 2，并将用户指定的诸产品放入 product_nums 列表中。
    #     如果是其他意图，返回 intention = 0。
    #     并将理由放在 reason 中。
    #     用户聊天历史记录为：{recent_messages}
    # '''

    prompt_user_summary_intention = f'''
        根据用户聊天历史，总结用户对旅行产品的需求，并判断用户的意图。
        结果放到 json 对象中，结构化返回。

        关于用户的需求总结：
        要以用户的口吻输出，不要以客服人员的角度总结。结果放在 input_summary 中。
        如果总结中涉及到已推荐产品，要带上产品编号，但不要带其标题。
        如果不涉及已推荐产品，就不用说"目前没有提到具体推荐的产品编号"这样的话。
        输出文字要平实，不要带文学色彩。要简短，不要啰嗦。

        关于用户的意图：
        如果用户感觉以前系统推荐的产品不太合适、或者不够多，希望再推荐些其他产品，返回 intention = 1。
        如果用户表示出对某个或某几个产品的肯定，或进一步询问已推荐的一个或几个产品的详细信息（如出发日期、价格、特点等），
        或想对比几个已推荐产品的某些特点，返回 intention = 2，并将用户指定的各产品编号（注意是以字母 U 打头的，不要漏了这个字母）放入 product_nums 列表中。
        如果是其他意图，返回 intention = 0。
        并将理由放在 reason 中。

        用户聊天历史记录为：{recent_messages}
    '''

    # messages_user_input = [{'role': 'user', 'content': prompt_user_input}]
    messages_condition = [{'role': 'user', 'content': prompt_condition}]
    # messages_user_intention = [{'role': 'user', 'content': prompt_user_intention}]
    messages_user_summary_intention = [{'role': 'user', 'content': prompt_user_summary_intention}]

    with ThreadPoolExecutor(max_workers=4) as executor:
        # f1 = executor.submit(qwen_call, messages_user_input, 'text', task_id, 'user_input_summary', model_name)  # 提交任务
        f2 = executor.submit(qwen_call, messages_condition, 'json_object', task_id, 'condition', config['model_user_condition'])
        # f3 = executor.submit(qwen_call, messages_user_intention, 'json_object', task_id, 'user_intention', model_name)
        f4 = executor.submit(qwen_call, messages_user_summary_intention, 'json_object', task_id, 'user_summary_intention', config['model_user_summary_intention'])

    # user_input_summary = f1.result()
    condition = json.loads(f2.result())
    # user_intention = json.loads(f3.result())
    user_summary_intention = json.loads(f4.result())

    # 意图识别时，如果没正面提到某些产品，可能没有 product_nums 字段。补一个，以防不测。
    # if 'product_nums' not in user_intention:
    #     user_intention['product_nums'] = []
    if 'product_nums' not in user_summary_intention:
        user_summary_intention['product_nums'] = []

    log.info(f'__ condition before adjust: {condition}')
    # qwen-plus 和 qwen-turbo 似乎都认为今年是 2023 年。临时解决方法：year += 2。注意 2024 是闰年。
    leap_date = datetime(year=2024, month=2, day=29)
    if condition['depart_date'] != '':
        depart_date = datetime.strptime(condition['depart_date'], '%Y-%m-%d')
        if depart_date.year < datetime.now().year:
            delta = 365 + 366 if depart_date < leap_date else 365 * 2
            condition['depart_date'] = (depart_date + timedelta(days=delta)).strftime('%Y-%m-%d')

    if condition['back_date'] != '':
        back_date = datetime.strptime(condition['back_date'], '%Y-%m-%d')
        if back_date.year < datetime.now().year:
            delta = 365 + 366 if back_date < leap_date else 365 * 2
            condition['back_date'] = (back_date + timedelta(days=delta)).strftime('%Y-%m-%d')

    return condition, user_summary_intention

def to_match_prompt(recent_messages, feature: str) -> list:
    # 如果用户的需求里涉及到多个产品，不用管，只看给定的这一个产品是否满足。
    prompt = f'''
        根据用户的对话历史，看给定的一个产品描述是否满足用户的旅游需求。结果放到 json 对象中，结构化返回。
        是否满足需求，放到 matched 变量中；原因，放到 reason 变量中。
        用户的对话历史：{recent_messages}
        旅游产品描述如下，只是一个产品：{feature}
    '''
    llm_messages = [{'role': 'user', 'content': prompt}]
    return llm_messages

def check_products_matched(recent_messages, full_features, task_id: str, model_name: str):
    if len(full_features) == 0:
        return []

    matched_product_nums = []
    with ThreadPoolExecutor(max_workers=len(full_features)) as executor:
        futures = {executor.submit(
            qwen_call, to_match_prompt(recent_messages, feature),
            'json_object', task_id, f'{pn} if_matched', model_name
        ): pn for pn, feature in full_features}

        for f in as_completed(futures):
            prod_name = futures[f]
            try:
                if f.result() == '': # 出错，只能跳过，无其他办法
                    log.info(f'{task_id} {model_name} {prod_name} if_matched wrong. skipped.')
                    continue
                res = json.loads(f.result())
                log.info(f'{task_id} {model_name} {prod_name} if_matched result:{res}')
                if res['matched']:
                    matched_product_nums.append(futures[f])
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for batch_features, e:{e}, prod_num:{prod_name}, trace: {trace_info}'
                print(f'__exception: {info}')
    return matched_product_nums

def to_content_prompt(recent_messages, feature: str) -> list:
    # 如果用户的需求里涉及到多个产品，不用管，只看给定的这一个产品是否满足。
    prompt = f'''
        结构化返回，结果放到 json 对象中，其中有且只有两个字段：content 和 score。
        根据产品信息，结合用户聊天历史中的需求，
        给出该产品的推荐理由（输出到 json 对象的 content 字段）和该产品与用户需求的相似度分数（输出到 json 对象的 score 字段，最高 100 分）。
        注意，已知该产品与用户需求比较相符。所以，归纳推荐理由时，请着重给出亮点。
        即使你认为它不太符合用户需求，也不要直接说它不合适，而是要用"虽然它不完全匹配，但也比较相关"这样的话术。
        用户的对话历史：{recent_messages}
        旅游产品信息：{feature}
    '''
    llm_messages = [{'role': 'user', 'content': prompt}]
    return llm_messages

def get_product_contents(recent_messages, prod_infos, task_id: str, model_name: str):
    if len(prod_infos) == 0:
        return []
    res_contents = []
    with ThreadPoolExecutor(max_workers=len(prod_infos)) as executor:
        futures = {executor.submit(
            qwen_call, to_content_prompt(recent_messages, p['full_feature']),
            'json_object', task_id, f"{p['product_num']} content", model_name
        ): p['product_num'] for p in prod_infos}

        # 大模型在极罕见情况下不返回 score。增加 sum_score, num_scores 及相关逻辑以容错。
        sum_score = 0
        num_scores = 0
        for f in as_completed(futures):
            product_num = futures[f]
            try:
                if f.result() == '': # 出错，只能跳过，无其他办法
                    log.info(f'{task_id} {model_name} {product_num} __content wrong__. skipped.')
                    continue
                res = json.loads(f.result())
                res['product_num'] = product_num
                if 'score' in res:
                    sum_score += res['score']
                    num_scores += 1
                log.info(f'{task_id} {model_name} {product_num} content:{res}')
                res_contents.append(res)
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for batch_features, e:{e}, prod_num:{product_num}, trace: {trace_info}'
                print(f'__exception: {info}')

    # 给没有 score 的产品手工增加 score
    num_contents = len(res_contents)
    if num_scores != num_contents:
        log.info(f'{task_id} {model_name} __content wrong__ {num_contents - num_scores} of {num_contents} products have no score')
        manual_score = 85 if num_scores == 0 else (sum_score // num_scores)
        for c in res_contents:
            if 'score' not in c:
                c['score'] = manual_score
                log.info(f'{task_id} {model_name} {product_num} __content wrong__ manual score: {manual_score}')
    return res_contents

if __name__ == '__main__':
    task_id = 'mock_task_id_1234'
    request_messages = [
        {
            "role": "user",
            "content": "您好，想去新加坡和马来西亚，大概一周时间，父母二人带一个十二岁男孩。有什么推荐吗？"
        },
        {"role": "assistant",
         "content": """为你推荐编号为 U174845 的产品，【众信制造：金牌南洋传奇】新加坡+马来西亚北京起止 5 晚 7 天。
      该产品的线路特色包括双峰塔-国家皇宫-广场-国家艺术馆-CITYWALK 城市单轨车-彩虹阶梯-阿罗街。
      此外，该产品还包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。
      出发地为北京，目的地为亚洲、新加坡。\n\n
      或者你也可以考虑编号为 U167657 的产品，北京起止【寻味南洋-米其林之旅】新加坡+马来西亚 7 天。
      该产品有两条线路可供选择，线路 A 是马进新出 CA871，线路 C 是大兴去首都回。产品特色是寻味南洋-米其林之旅，
      你可以品尝到当地的美食。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、
      行程所含景点（区）门票等。出发地为北京，目的地为亚洲、马来西亚和亚洲、新加坡。\n\n
      如果你从河南郑州出发，还可以选择编号为 U179033 的产品，【新加坡乐园 MAX】郑州起止 4 晚 6 天。
      该产品升级 2 晚国际四星，包含新加坡环球影城+飞禽动物园+日间动物园三大乐园精彩之行。费用包含机票费用、
      行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、中文导游服务、境外旅游人身意外险、行程所含景点（区）门票等。
      出发地为河南郑州，目的地为亚洲、新加坡。"""
         },
        {
            "role": "user",
            "content": "第1个、第三个都还行。麻烦帮我好好规划一下。"  # 这几个都不错。你帮我好好做个比较，我最后从中选一个"
        }
    ]

    request_messages = [{'role': 'user', 'content': '想要去欧洲度蜜月，大概10天左右'}, {'role': 'assistant',
                                                                                       'content': '根据用户需求，以下是推荐的产品： 编号为U167001的产品【盈尚·秒杀四国】德国+法国+意大利+瑞士11/12/13天：虽然它不是10天的行程，但其丰富的景点和较为灵活的安排比较相关，适合蜜月旅行。. 编号为U166937的产品【尊悦·王牌四国】一价全含德法意瑞4国13天：这条线路包含了多个著名景点，行程安排较为深入，适合想要在欧洲度过一段浪漫时光的情侣。 编号为U170548的产品【深圳出发】法瑞意德+郁金香一价全含13天：这条线路除了经典的欧洲景点外，还包含了库肯霍夫郁金香公园和哈勒森林风信子等浪漫元素，非常适合蜜月旅行。'},
                        {'role': 'user', 'content': '哪个适合十一期间的'}]

    t00 = datetime.now()
    model_name = 'qwen-turbo'
    res = analyze_user_input(request_messages, task_id, model_name)
    log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
    log.info(f'/get_task_id {task_id} {model_name}.condition:{res[0]}')
    log.info(f'/get_task_id {task_id} {model_name}.summary_intention:{res[1]}')
    sys.exit(1)

    # dates = [ '一周', '半个月', '三五天', '十天半个月', '七八天', '10天', '3天', ]
    # dates = [ '今年暑假', '明年春节', '国庆', '五一', '劳动节', '下周', '今年开斋节', ]
    dates = ['五一']

    for d in dates:
        # log.info(f'_{d}_')
        # request_messages = [
        #     {
        #         "role": "user",
        #         "content": f"您好，想{d}期间加坡和马来西亚，大概半个月时间，父母二人带一个十二岁男孩。有什么推荐吗"
        #     },
        # ]
        # request_messages = [
        #     {'role': 'user', 'content': '有天山相关的旅游产品吗。想五一期间去，玩一周左右吧。'},
        #     # {"role": "assistant",
        #     #  "content": "编号为U184563的产品“【杏好遇见】双飞8日游”包含天山天池景点，行程中会游览天山天池风景区，体验瑶池仙境。成人售价4980.0元，出发日期2025-04-08，返回日期2025-04-15，目前有6个库存。"},
        #     # {'role': 'user', 'content': '这个感觉不太好。再帮我推荐点别的更合适的吧'},
        # ]

        request_messages = [{'role': 'user', 'content': '想要去欧洲度蜜月，大概10天左右'}, {'role': 'assistant',
                                                                                   'content': '根据用户需求，以下是推荐的产品： 编号为U167001的产品【盈尚·秒杀四国】德国+法国+意大利+瑞士11/12/13天：虽然它不是10天的行程，但其丰富的景点和较为灵活的安排比较相关，适合蜜月旅行。. 编号为U166937的产品【尊悦·王牌四国】一价全含德法意瑞4国13天：这条线路包含了多个著名景点，行程安排较为深入，适合想要在欧洲度过一段浪漫时光的情侣。 编号为U170548的产品【深圳出发】法瑞意德+郁金香一价全含13天：这条线路除了经典的欧洲景点外，还包含了库肯霍夫郁金香公园和哈勒森林风信子等浪漫元素，非常适合蜜月旅行。'},
                    {'role': 'user', 'content': '哪个适合十一期间的'}]
        t00 = datetime.now()
        model_name = 'qwen-turbo'
        res = analyze_user_input(request_messages, task_id, model_name)
        log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
        log.info(f'/get_task_id {task_id} {model_name}.condition:{res[0]}')
        log.info(f'/get_task_id {task_id} {model_name}.summary_intention:{res[1]}')

        # import time
        # time.sleep(1)
        # t00 = datetime.now()
        # model_name = 'qwen-turbo'
        # res = analyze_user_input(request_messages, task_id, model_name)
        # log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
        # log.info(f'/get_task_id {task_id} {model_name}.user_input_summary:{res[0]}')
        # log.info(f'/get_task_id {task_id} {model_name}.condition:{res[1]}')
        # log.info(f'/get_task_id {task_id} {model_name}.intention:{res[2]}')
        # log.info(f'/get_task_id {task_id} {model_name}.summary_intention:{res[3]}')
