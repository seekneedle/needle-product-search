import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))  # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

import asyncio
import aiohttp
import json
from utils.config import config
from utils.log import log
from utils.security import decrypt
from server.response import RequestError


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

    # coze workflow 返回格式：https://www.coze.cn/open/docs/developer_guides/workflow_run
    retries = 0
    while retries < 3:
        log.info(f'coze_call_async wf:{wf_id} retries:{retries} before aiohttp.post')
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                log.info(f'coze_call_async wf:{wf_id} retries:{retries} after aiohttp.post')
                if response.status == 200:
                    response_data = await response.json()
                    # log.info(f'coze_call_async wf:{wf_id} retries:{retries} http ok, response:{response_data}')
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



# obsoleted
def get_product_feature(product_num: str) -> str:
    log.info(f'coze_wf.get_product_feature: product_num:{product_num}')
    wf_id_name = 'coze_product_feature_wf_id'
    params = {
        'product_num': product_num,
        'env': config['env']
    }
    response = coze_workflow_sync(wf_id_name, params)
    product_detail = response['product_feature']
    return product_detail


#
# 返回结果形如：
# {
#   'questions': [
#       'U174845产品的具体行程安排是怎样的？',
#       'U167657产品两条线路有什么区别？',
#       'U179033产品在三大乐园分别玩多久？'
#   ]
# }
#
async def get_questions(messages) -> dict:
    wf_id_name = 'coze_product_questions_wf_id'
    params = {
        'env': config['env'],
        'messages': messages
    }
    res = await coze_workflow_async(wf_id_name, params)
    return res


if __name__ == '__main__':
    messages = [
        {
            "role": "user",
            "content": "您好，想去新加坡和马来西亚，大概一周时间，父母二人带一个十二岁男孩。有什么推荐吗？"
        },
        {"role": "assistant",
         "content": "为你推荐编号为 U174845 的产品，【众信制造：金牌南洋传奇】新加坡+马来西亚北京起止 5 晚 7 天。该产品的线路特色包括双峰塔-国家皇宫-广场-国家艺术馆-CITYWALK 城市单轨车-彩虹阶梯-阿罗街。此外，该产品还包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、新加坡。\n\n或者你也可以考虑编号为 U167657 的产品，北京起止【寻味南洋-米其林之旅】新加坡+马来西亚 7 天。该产品有两条线路可供选择，线路 A 是马进新出 CA871，线路 C 是大兴去首都回。产品特色是寻味南洋-米其林之旅，你可以品尝到当地的美食。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、境外旅游人身意外险、行程所含景点（区）门票等。出发地为北京，目的地为亚洲、马来西亚和亚洲、新加坡。\n\n如果你从河南郑州出发，还可以选择编号为 U179033 的产品，【新加坡乐园 MAX】郑州起止 4 晚 6 天。该产品升级 2 晚国际四星，包含新加坡环球影城+飞禽动物园+日间动物园三大乐园精彩之行。费用包含机票费用、行程所列酒店住宿、当地空调旅游巴士、行程中所列餐食、中文导游服务、境外旅游人身意外险、行程所含景点（区）门票等。出发地为河南郑州，目的地为亚洲、新加坡。"
         },
        # {
        #     "role": "user",
        #     "content": "嗯，我们不希望太累，想轻松点。从北京出发。"
        # }
    ]
    res = asyncio.run(get_questions(messages))
    log.info(f'____{type(res)} __ {res}____')
