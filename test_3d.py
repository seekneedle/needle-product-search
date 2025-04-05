import requests
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import traceback
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.log import log
import base64

import multiprocessing
import time
import os

# http://8.152.213.191:8401/product/request_product_search
# http://8.152.213.191:8401/product/get_summary_result
# http://8.152.213.191:8401/product/get_products_result/{task_id}

# 'c862c843-b6b5-4a85-85cb-b6b5e5e00487' # 导致豆包运行错误的

# 【有关于冰与火之歌相关主体的旅游产品冰与火这个，只收到了 get_task_id 的请求，
# 没收到后续的两个 get summary 和 get contents 的请求。是否前端程序因为什么原因没有发后续请求？
# （但从 log 里看，用户先问天山，没等到回答，就又问了冰与火。）

# 【有关于冰与火之歌相关主体的旅游产品吗】：517889a8-b62d-4090-b15d-fb1f3f019c16
# 【有天山相关的旅游产品吗】：ccbaa9ae-f138-4063-b070-6aae931f7f46




env = 'prod'
max_num = 5


messages = [
  {
    "role" : "user",
    "content" : "您好，想去新加坡和马来西亚，大概一周时间，父母二人带一个十二岁男孩。有什么推荐吗？"
  },
  { "role": "assistant",
  "content": "为你推荐编号为 U174845 的产品，【众信制造：金牌南洋传奇】新加坡+马来西亚北京起止 5 晚 7 天。该产品的线路特色包括双峰塔-国家皇宫-广场-国家艺术馆-CITYWALK 城市单轨车-彩虹阶梯-阿罗街。此外，该产品还包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、新加坡。\n\n或者你也可以考虑编号为 U167657 的产品，北京起止【寻味南洋-米其林之旅】新加坡+马来西亚 7 天。该产品有两条线路可供选择，线路 A 是马进新出 CA871，线路 C 是大兴去首都回。产品特色是寻味南洋-米其林之旅，你可以品尝到当地的美食。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、马来西亚和亚洲、新加坡。\n\n如果你从河南郑州出发，还可以选择编号为 U179033 的产品，【新加坡乐园 MAX】郑州起止 4 晚 6 天。该产品升级 2 晚国际四星，包含新加坡环球影城+飞禽动物园+日间动物园三大乐园精彩之行。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、中文导游服务、境外旅游人身意外险、行程所含景点（区）门票等。出发地为河南郑州，目的地为亚洲、新加坡。"
  },
  {
    "role": "user",
    "content": "嗯，我们不希望太累，想轻松点。从北京出发。"
  }
]

messages = [
    {'role': 'user', 'content': '有天山相关的旅游产品吗'}, 
    {'role': 'assistant', 'content': None}, 
    {'role': 'user', 'content': '有关于冰与火之歌相关主体的旅游产品吗'}
]

messages = [
    { "role" : "user", "content" : "推荐一个适合小孩儿的旅游产品" }
]

messages = [
    {'role': 'user', 'content': '有天山相关的旅游产品吗'}, 
]

messages = [
    {'role': 'user', 'content': '有关于冰与火之歌相关主体的旅游产品吗'}, 
]

username = 'needle_product_search'

password = 'needle_product_search'
url0 = 'http://localhost:8405'

# password = 'u^rk*uLxmQ7yBMJc'
# url0 = 'http://8.152.213.191:8401'

encoded_auth = base64.b64encode(f'{username}:{password}'.encode()).decode()
auth = f'Basic {encoded_auth}'
headers = {
    'Content-Type': 'application/json',
    'Authorization': auth
}


def task_id_call(env: str, max_num: int, messages) -> str:
    url = f'{url0}/product/request_product_search'
    data = {
        'env': env,
        'maxNum' : max_num,
        'messages': messages
    }
    print('\n' + '-' * 80 + 'task id' + '\n')
    response = requests.post(url, headers=headers, json=data)
    # {
    #     'code': 200,
    #     'status': 'success', 
    #     'data': {'taskId': '66bff6cb-a87e-4e3e-bb2f-7d6949d228cf'}
    # }

    task_id = response.json()['data']['taskId']
    print(f'task_id: {task_id}')
    return task_id

def summary_call(task_id: str):
    url = f'{url0}/product/get_summary_result'
    data = {
        'taskId': task_id,
    }
    print('\n' + '-' * 80 + 'summary' + '\n')
    response = requests.post(url, headers=headers, json=data, stream=True)
    prefix = b'data: '
    for line in response.iter_lines():
        if line and line.startswith(prefix):
            data = line[len(prefix):]
            print("received: ", data.decode('utf-8') )

def content_call(task_id: str):
    url = f'{url0}/product/get_products_result/{task_id}'
    print('\n' + '-' * 80 + 'content' + '\n')
    response = requests.get(url, headers=headers)
    # {
    #     'code': 200,
    #     'status': 'success',
    #     'data': {
    #         'products': [
    #             {'content': '...', 'product_num': 'U184448', 'score': 80},
    #             {'content': '...', 'product_num': 'U184243', 'score': 60},
    #             {'content': '...', 'product_num': 'U182800', 'score': 40}
    #         ]
    #     }
    # }
    print(response.json()['data'])

def line_valid(task_id: str) -> bool:
    if '__qwen_stream_call' in line or '__coze_call_async ' in line:
        return True
    if task_id not in line:
        return False
    if f'{task_id} summary' in line or f'{task_id} products:' in line:
        return False
    return True


# 多线程并发调用 summary 和 content，为了造成 http server 那边的真并发请求。
# 恰好这两个调用的返回结果也互不影响

if __name__ == '__main__':
    task_id = task_id_call(env, max_num, messages)
    print(f'task_id: {task_id}')

    task_id = '8693852d-1488-4e49-a493-3ae61be7e695'
    p1 = multiprocessing.Process(target=summary_call, args=(task_id,))
    print('summary created')

    p2 = multiprocessing.Process(target=content_call, args=(task_id,))
    print('content created')

    p1.start()
    print('summary started')

    p2.start()
    print('content started')

    p1.join()
    print('summary joined')
    p2.join()
    print('content joined')

    program_file_path = os.path.abspath(__file__)
    dir_path = os.path.dirname(program_file_path)
    log_file_path = os.path.join(dir_path, 'output/server.log')
    print(log_file_path)
    print(f'task_id: {task_id}')
    for line in open(log_file_path, 'r'):
        if line_valid(task_id):
            print(line.strip().replace(task_id, '').replace('- INFO - ', ''))

