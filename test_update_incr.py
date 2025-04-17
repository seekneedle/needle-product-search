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

username = 'needle_product_search'
# password = 'needle_product_search'

password = 'u^rk*uLxmQ7yBMJc'
url0 = 'http://localhost:8409'

# url0 = 'http://8.152.213.191:8409'



# 多个 message，为测试并发
product_nums_lists = [
    [ "U180123", 'U166879', 'U172219' ],
    ['U170672', 'U174661', 'U176167', 'U175778', 'U176189', 'U180058', 'U172025'],
    ['U182551', 'U179149', 'U173902', 'U185910', 'U186332'],
    ['U175234', 'U175256', 'U177425', 'U175330', 'U175360'],
    ['U167304', 'U168649', 'U167553'],
    ['U169828', 'U174670', 'U177906', 'U185089'],
    ['U169828', 'U174670', 'U177906', 'U185089'],
    ['U184321'],
    ['U172645'],
    ['U185208'],
    ['U167501'],
    ['U177586'],
    ['U178374'],
    ['U168657'],
    ['U166889'],
    ['U175560'],
    ['U168829'],
    ['U174680'],
    ['U166854'],
    ['U170284'],
]

product_nums_lists = [
    [],
    ['U168829'],
    ['U174680'],
    ['U166854'],
    ['U170284'],
]




encoded_auth = base64.b64encode(f'{username}:{password}'.encode()).decode()
auth = f'Basic {encoded_auth}'
headers = {
    'Content-Type': 'application/json',
    'Authorization': auth
}


def update_incr_call(product_nums: list) -> str:
    url = f'{url0}/product/increment_update'
    data = {
      "type": "add",
      "productNums" : product_nums
    }
    print('\n' + '-' * 80 + f'{product_nums}\n')
    response = requests.post(url, headers=headers, json=data)
    print(response)
    print(response.text)

# 多线程并发调用，为了造成 http server 那边的真并发请求。
# 恰好这两个调用的返回结果也互不影响

if __name__ == '__main__':
    processes = []
    for num_list in product_nums_lists:
        p = multiprocessing.Process(target=update_incr_call, args=(num_list,))
        p.start()

    for p in processes:
        p.join()

    for num_list in product_nums_lists:
        # call to get status, wait until all done
        pass
