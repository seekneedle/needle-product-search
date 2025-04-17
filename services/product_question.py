from pydantic import BaseModel
from typing import List
from typing import Optional

from data.search import SearchEntityExx
from server.response import RequestError
from utils.config import config
from utils.security import decrypt
from utils import coze_wf
from utils.log import log


class ProductQuestionRequest(BaseModel):
    is_uux: Optional[int] = 0
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True

class ProductQuestionResponse(BaseModel):
    questions: List[object] # todo: or string?


async def product_question(request: ProductQuestionRequest):
    log.info(f'/get_question product_question() begins')
    if request.is_uux != 0 or not request.messages:
        parsed_data = {'questions': []}
        response = ProductQuestionResponse(**parsed_data)
        return response

    recent_messages = request.messages[-11:]
    parsed_data = await coze_wf.get_questions(recent_messages)
    return ProductQuestionResponse(**parsed_data)

    # start_time = datetime.now()
    # timeout = timedelta(seconds=60)
    # poll_interval = 0.2  # seconds
    #
    # data_ready = False
    # while datetime.now() - start_time < timeout:
    #     tt0 = datetime.now()
    #     search_entity = SearchEntityExx.query_first(task_id=task_id)
    #     #
    #     # 上面 tt0 和 下面 log 用于调试并发问题
    #     #
    #     log.info(f'/get_summary_result {task_id} query_first costs {datetime.now() - tt0}')
    #     if search_entity:
    #         data_ready = True
    #         break
    #     await asyncio.sleep(poll_interval)
    #
    # waited = datetime.now() - start_time
    # if not data_ready:  # 超时：前面 get_task_id 出错了
    #     log.info(f'/get_question {task_id} timeout costs {waited}. return.')
    #      # 'data: 不好意思，似乎出了些问题，目前没有可以推荐的\n\n'
    #     return
    #
    # log.info(f'/get_question {task_id} data ready costs {waited}')
    #
    # if search_entity.user_input_summary == '':
    #     log.info(f'/get_summary_result {task_id} db.user_input_summary empty. return.')
    #     # yield 'data: 不好意思，似乎出了些问题，目前没有可以推荐的\n\n'
    #     return
    #

    # url = config['coze_api_url']
    # headers = {
    #     'Content-Type': 'application/json',
    #     'Authorization': decrypt(config['coze_api_auth'])
    # }
    # data = {
    #     "workflow_id": config['coze_product_questions_wf_id'],
    #     "parameters": {
    #         "env": config['env'],
    #         "messages": request.messages
    #     }
    # }
    # response = requests.post(url, headers=headers, json=data)
    # if response.status_code == 200:
    #     response_data = response.json()
    #     input_data = response_data["data"]
    #     try:
    #         parsed_data = json.loads(input_data)
    #         response = ProductQuestionResponse(**parsed_data)
    #         return response
    #     except json.JSONDecodeError:
    #         raise RequestError(response.status_code, f"解析失败: {response.status_code}, 响应内容: {response.text}")
    # else:
    #     raise RequestError(response.status_code, f"请求失败: {response.status_code}, 响应内容: {response.text}")