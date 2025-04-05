from openai import OpenAI
from utils.security import decrypt
from utils.config import config
from utils.log import log
import multiprocessing
import asyncio

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

def qwen_stream_call(messages, queue):
    log.info('__qwen_stream_call get_summary REALLY before calling qwen')
    completion = client.chat.completions.create(
        model='qwen-plus-2024-09-19',
        messages=messages,
        stream=True,
        stream_options={'include_usage': True}
    ) # 貌似是第一个 chunk 返回时才返回
    log.info('__qwen_stream_call get_summary REALLY after calling qwen')
    cnt = 0
    for chunk in completion:
        if len(chunk.choices) > 0:
            if cnt == 0:
                log.info('__qwen_stream_call get_summary REALLY first chunk received')
            cnt += 1
            queue.put(f'data: {chunk.choices[0].delta.content}\n\n')
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
