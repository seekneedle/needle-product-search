from openai import OpenAI
from utils.security import decrypt
from utils.config import config
from utils.log import log
import multiprocessing
import asyncio
from datetime import datetime

client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

def generate(messages):
    completion = client.chat.completions.create(
        model='qwen-plus-2024-09-19',
        messages=messages
    )
    return completion.choices[0].message.content

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


# 去掉 log 的版本。（log 很多的版本，见本文件最下方）
def qwen_stream_call(messages, queue):
    completion = client.chat.completions.create(
        # model='qwen-plus-2024-09-19',
        # model='qwq-plus',
        # model='qwen-plus',
        model='qwen-turbo',
        messages=messages,
        stream=True, # QwQ 模型仅支持流式输出方式调用
        stream_options={'include_usage': False} # 不需要得到 token 使用情况统计
    ) # 貌似是第一个 chunk 返回时才返回
    for chunk in completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content is not None: # 真正的回复
            queue.put(f'data: {delta.content}\n\n')
    queue.put(None)

async def stream_generate_ex(messages):
    log.info('__qwen_stream_call get_summary WRAPPER before calling qwen')
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=qwen_stream_call, args=(messages, queue))
    log.info('__qwen_stream_call get_summary WRAPPER before process.start()')
    process.start()
    log.info('__qwen_stream_call get_summary WRAPPER after process.start()')

    try:
        cnt = 0
        while True:
            # 异步监听队列（避免阻塞事件循环）
            data = await asyncio.get_event_loop().run_in_executor(
                None,  # 使用默认线程池
                queue.get  # 阻塞调用，但通过线程池转为异步
            )
            if cnt == 0:
                log.info('__qwen_stream_call get_summary WRAPPER first chunk received')
            cnt += 1
            if data is None: # 结束信号
                break
            yield data  # 返回 SSE 数据
    finally:
        process.join()  # 确保进程退出

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
