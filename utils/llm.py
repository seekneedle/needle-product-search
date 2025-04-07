import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent)) # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

from openai import OpenAI
from utils.security import decrypt
from utils.config import config
from utils.log import log
import multiprocessing
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json

client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

def qwen_call(messages, return_type: str, task_id: str, job_name: str, model_name: str):
    # task_id 和 job_name 只用于 logging 目的
    log.info(f'{model_name} {task_id} {job_name} begins')
    t0 = datetime.now()
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={'type': return_type}
    )
    log.info(f'{model_name} {task_id} {job_name} done, cost {datetime.now() - t0}')
    return completion.choices[0].message.content

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
    log.info(f'{model_name} stream_call {task_id} {job_name} WRAPPER before calling qwen')
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=qwen_stream_call, args=(messages, queue, model_name))
    log.info(f'{model_name} stream_call {task_id} {job_name} WRAPPER before process.start()')
    process.start()
    log.info(f'{model_name} stream_call {task_id} {job_name} WRAPPER after process.start()')

    try:
        cnt = 0
        while True:
            # 异步监听队列（避免阻塞事件循环）
            data = await asyncio.get_event_loop().run_in_executor(
                None,  # 使用默认线程池
                queue.get  # 阻塞调用，但通过线程池转为异步
            )
            if cnt == 0:
                log.info(f'{model_name} stream_call {task_id} {job_name} WRAPPER first chunk received')
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
def analyze_user_input(user_messages: list, task_id: str, model_name: str):
    prompt_user_input = f'''
        根据用户聊天历史，总结用户对旅行产品的需求。要以用户的口吻输出，不要以客服人员的角度总结。
        如果总结中涉及到已推荐产品，要带上产品编号，但不要带其标题。
        如果不涉及已推荐产品，就不用说"目前没有提到具体推荐的产品编号"这样的话。
        输出文字要平实，不要带文学色彩。要简短，不要啰嗦。
        用户聊天历史记录为：{user_messages}
    '''

    recent_messages = user_messages[-11:]
    prompt_condition = f'''
        ### 角色
        根据客户user的聊天历史，总结客户对于出行时间、产品价格、产品存量的需求，放到 json 对象中，结构化返回。

        ### 能力1：提取产品出行时间要求
        1. 根据聊天历史，提取客户希望的出发时间到depart_date，如果没有提及出发时间，则输出空。
        2. 根据聊天历史，提取客户希望的返回时间到back_date，如果没有提及返回时间，则输出空。
        3. 提取格式为yyyy-MM-dd，比如：2025-06-29。

        ### 能力2： 提取产品存量要求
        1. 根据聊天历史，提取客户要求的最少存量，存量不能小于1。
        2. 如果用户没有提及最小存量，默认为1.
        3. 输出存量要求必须是整数。

        ### 能力3： 提取产品价格要求
        1. 根据聊天历史，提取客户要求的最低价格，如果没有提及最低价格，则最低价格输出0。
        2. 根据聊天历史，提取客户要求的最高价格，如果没有提起最高价格，则最高价格输出空。

        ### 限制
        1. 不允许编造内容。
        2. 必须严格按照客户聊天历史中的信息进行提取。

        ### 用户聊天历史

        {recent_messages}
'''

    prompt_user_intention = f'''
        根据用户聊天历史，判断用户最后的意图。结果放到 json 对象中，结构化返回。
        如果用户感觉以前系统推荐的产品不太合适、或者不够多，希望再推荐些其他产品，返回 intention = 1。
        如果用户表示出对某个或某几个产品的肯定，或进一步询问已推荐的一个或几个产品的详细信息（如出发日期、价格、特点等），或想对比几个已推荐产品的某些特点，返回 intention = 2，并将用户指定的诸产品放入 product_nums 列表中。
        如果是其他意图，返回 intention = 0。
        并将理由放在 reason 中。
        用户聊天历史记录为：{user_messages}
    '''

    messages_user_input = [{'role': 'user', 'content': prompt_user_input}]
    messages_condition = [{'role': 'user', 'content': prompt_condition}]
    messages_user_intention = [{'role': 'user', 'content': prompt_user_intention}]

    with ThreadPoolExecutor(max_workers=1) as executor:
        # f1 = executor.submit(qwen_call, messages_user_input, 'text', task_id, 'user_input_summary', model_name)  # 提交任务
        # f2 = executor.submit(qwen_call, messages_condition, 'json_object', task_id, 'condition', model_name)
        f3 = executor.submit(qwen_call, messages_user_intention, 'json_object', task_id, 'user_intention', model_name)
        # res1 = f1.result()
        # res2 = f2.result()
        res3 = f3.result()

    return (json.loads(res3),)
    # return (res1, json.loads(res2), json.loads(res3))


if __name__ == '__main__':
    task_id = 'mock_task_id_1234'
    request_messages = [
        {
            "role": "user",
            "content": "您好，想去新加坡和马来西亚，大概一周时间，父母二人带一个十二岁男孩。有什么推荐吗？"
        },
        {
            "role": "assistant",
            "content": "为你推荐编号为 U174845 的产品，【众信制造：金牌南洋传奇】新加坡+马来西亚北京起止 5 晚 7 天。该产品的线路特色包括双峰塔-国家皇宫-广场-国家艺术馆-CITYWALK 城市单轨车-彩虹阶梯-阿罗街。此外，该产品还包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、新加坡。\n\n或者你也可以考虑编号为 U167657 的产品，北京起止【寻味南洋-米其林之旅】新加坡+马来西亚 7 天。该产品有两条线路可供选择，线路 A 是马进新出 CA871，线路 C 是大兴去首都回。产品特色是寻味南洋-米其林之旅，你可以品尝到当地的美食。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、马来西亚和亚洲、新加坡。\n\n如果你从河南郑州出发，还可以选择编号为 U179033 的产品，【新加坡乐园 MAX】郑州起止 4 晚 6 天。该产品升级 2 晚国际四星，包含新加坡环球影城+飞禽动物园+日间动物园三大乐园精彩之行。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、中文导游服务、境外旅游人身意外险、行程所含景点（区）门票等。出发地为河南郑州，目的地为亚洲、新加坡。"
        },
        {
            "role": "user",
            "content": "这几个都不错，帮我比较一下它们的特色吧，排个序",
            # "content": "嗯，我们不希望太累，想轻松点。从北京出发。费用不是问题，至少五万起。要快，本周末之前必须出发。"
        }
    ]

    t00 = datetime.now()
    model_name = 'qwen-plus'
    user_analysis_qwen = analyze_user_input(request_messages, task_id, model_name)
    log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
    # log.info(f'/get_task_id {task_id} {model_name}.user_input_summary:{user_analysis_qwen[0]}')
    # log.info(f'/get_task_id {task_id} {model_name}.condition:{user_analysis_qwen[1]}')
    log.info(f'/get_task_id {task_id} {model_name}.intention:{user_analysis_qwen[0]}')
