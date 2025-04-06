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


    # log.info(f'/get_task_id {task_id} user_input_summary:{user_input_summary}')
    # log.info(f'/get_task_id {task_id} condition:{condition}')

def line_valid(task_ids: list) -> str:
    if '/request_product_search received request' in line or '__qwen_stream_call' in line or '__coze_call_async ' in line:
        return line.strip().replace('- INFO - ', '')
    for i, task_id in enumerate(task_ids):
        if (task_id in line
                and f'{task_id} summary' not in line
                and f'{task_id} products:' not in line
                and f'/get_task_id {task_id} condition:' not in line):
            return line.strip().replace(task_id, f'T{i}').replace('- INFO - ', '')
    return ''

def line_valid_feature(task_id: str) -> bool:
    if '_feature concurrent ' in line or ' db.get_dynamic_features costs ' in line or ' db.get_product_features costs ' in line:
        return True
    else:
        return False

# 多线程并发调用 summary 和 content，为了造成 http server 那边的真并发请求。
# 恰好这两个调用的返回结果也互不影响

if __name__ == '__main__':

    test_name = 'test8'

    task_id_dict = {
        'test1' : ['3e5bf885-f498-46d5-bede-67e5bf67165b', '6d6be93e-2719-4d03-ae5b-dfbb5cc730ae'],
        'test2' : ['a25d96e6-ac58-4fbf-a4bc-899ddcf32898', '9fb912e6-42af-4cf0-9f40-ec6bca4c42b8'],
        'test3' : ['9c90c99f-37b4-45cc-964f-f3e1fffd6317', '00e3139d-0dde-4ab0-8311-dc34a9635e5f'],
        'test4' : ['47ddcd62-74e9-4a02-aa32-9e049040f7f1', ],
        'test5' : ['51f31a08-ae9a-4391-a70a-065e81ede0b4', ],
        'test6' : ['475ad66f-821c-4d8f-9f15-db7adc89e586', ],
        'test7' : ['c69fe5ce-16c0-474c-afad-ca3ee8bce43e', '4d4766a3-898c-484c-aa61-15e299442a43', 'a0e85e04-e534-4d18-b62b-4692b94abc22', '0db1c3f8-c9b3-44cd-bb90-e8a577c44f4a', ],
        'test8' : ['0db1c3f8-c9b3-44cd-bb90-e8a577c44f4a', '204e31a2-92a3-477e-9f75-da7cc6118e10', '2b86c583-59bf-4707-8028-77437553b19c', '3bb26b7d-803b-45b1-97e7-c6ebc4b8d4da', '4d4766a3-898c-484c-aa61-15e299442a43', '6afa1087-3660-47da-b4ba-018ddbaa0a75', '8b7597ce-cae7-443a-bb2b-23108f8d98a0', 'a0e85e04-e534-4d18-b62b-4692b94abc22', 'c69fe5ce-16c0-474c-afad-ca3ee8bce43e', 'f5d4daed-9f45-43b0-8321-068fb851330e', 'f6175d72-9a46-4551-bc4d-551b1c23ca58',]
    }
    task_ids = task_id_dict[test_name]

    program_file_path = os.path.abspath(__file__)
    dir_path = os.path.dirname(program_file_path)
    log_orig_file_path = os.path.join(dir_path, f'output/server.log')
    log_file_path = os.path.join(dir_path, f'output/server.log.{test_name}.orig')
    res_file_path = os.path.join(dir_path, f'mylog.for.{test_name}.md')
    print(log_file_path)
    print(res_file_path)

    import shutil
    shutil.copy(log_orig_file_path, log_file_path)

    with open(res_file_path, 'w') as ofile:
        for line in open(log_file_path, 'r'):
            l = line_valid(task_ids)
            if l:
                ofile.write(l)
                ofile.write('\n')

    poll_res_file_path = os.path.join(dir_path, f'mylog.for.{test_name}.poll.analysis.md')
    for ti, task_id in enumerate(task_ids):
        print('\n', '_' * 40, ti, task_id, '\n')
        tag_summary = f' - /get_summary_result T{ti} query_first costs '
        tag_content = f' - /get_products_result T{ti} query_first costs '
        first_summary_arrived = False
        first_content_arrived = False
        prev_summary_time = datetime.now()
        prev_content_time = datetime.now()
        prev_summary_lineno = 0
        prev_content_lineno = 0
        for idx, line in enumerate(open(res_file_path, 'r')):
            if tag_summary not in line and tag_content not in line:
                continue
            line_no = idx + 1
            t = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f')
            if tag_summary in line:
                if not first_summary_arrived:
                    first_summary_arrived = True
                    print(f'summary, line {line_no}, first poll: {t}')
                else:
                    delta = t - prev_summary_time
                    if delta > timedelta(seconds=0.3) or delta < timedelta(seconds=0.1):
                        print(f'summary, line {line_no}, prev {prev_summary_lineno}, poll interval abnormal:{delta}')
                prev_summary_time = t
                prev_summary_lineno = line_no
            if tag_content in line:
                if not first_content_arrived:
                    first_content_arrived = True
                    print(f'content, line {line_no}, first poll: {t}')
                else:
                    delta = t - prev_content_time
                    if delta > timedelta(seconds=0.3) or delta < timedelta(seconds=0.1):
                        print(f'content, line {line_no}, prev {prev_content_lineno}, poll interval abnormal:{delta}')
                prev_content_time = t
                prev_content_lineno = line_no
        print(f'summary, line {prev_summary_lineno}, last poll: {prev_summary_time}')
        print(f'content, line {prev_content_lineno}, last poll: {prev_content_time}')

    for idx, line in enumerate(open(res_file_path, 'r')):
        line_no = idx + 1
        t = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f')
        if ' - /request_product_search received request:' in line:
            print(f'line {line_no}, {t}, /task_id request arrived.')
            continue
        for ti, task_id in enumerate(task_ids):
            tn = f'T{ti}'
            if f' - /get_products_result {tn} data ready ' in line:
                print(f'line {line_no}, {t}, {tn} content data ready, will call coze workflow')
            elif f' - /get_summary_result {tn} data ready ' in line:
                print(f'line {line_no}, {t}, {tn} summary data ready, will call qwen')
            elif f' - /get_summary_result {tn} all chunks arrived.' in line:
                print(f'line {line_no}, {t}, {tn} summary chunks complete')
            elif f' - /get_summary_result {tn} first chunk arrived.' in line:
                print(f'line {line_no}, {t}, {tn} summary chunks begins')
            elif f' - /get_products_result {tn} api request costs' in line:
                print(f'line {line_no}, {t}, {tn} content complete')
            # elif f' - /get_summary_result {tn} before calling qwen' in line:
            #     print(f'line {line_no}, {t}, {tn} summary will call qwen')
            # elif f' - /get_products_result {tn} before wf.get_contents' in line:
            #     print(f'line {line_no}, {t}, {tn} content will call coze workflow')
            elif f' - /get_task_id {tn} retrieve_products_bg() begins' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id fire_forget_worker begins')
            elif f' - /get_task_id {tn} wf.get_input_summary_and_condition before coze_call_sync' in line or f' - /get_task_id {tn} wf.analyze_user_input before coze_call_sync' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id analyze_user_input begins')
            elif f' - /get_task_id {tn} wf.get_input_summary_and_condition costs ' in line or f' - /get_task_id {tn} wf.analyze_user_input costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id analyze_user_input complete')
            elif f' - /get_task_id {tn} kb.retrieve costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id retrieve_knowledge_base complete')
            elif f' - /get_task_id {tn} db.get_dynamic_features costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id db.get_dynamic_features complete')
            elif f' - /get_task_id {tn} co.retrieve_kb_dynamic_features total costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id retrieve_kb & dynamic_fatures complete')
            elif f' - /get_task_id {tn} db.get_product_features costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id db.get_product_features complete')
            elif f' - /get_task_id {tn} retrieve_products_bg() total costs ' in line:
                print(f'line {line_no}, {t}, {tn} get_task_id fire_forget_worker complete')