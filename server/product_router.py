from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import traceback
from datetime import datetime
import time

from server.auth import check_permission

from utils.log import log
from services.product_search import product_search, ProductSearchRequest, ProductSearchTaskResponse, get_summary, get_products, get_task_id
from services.product_compare import product_compare, ProductCompareRequest
from services.product_update import product_update
from services.product_increment_update import product_increment_update, ProductUpdateIncrRequest
from services.product_question import product_question, ProductQuestionRequest
from server.response import SuccessResponse, FailResponse
from pydantic import BaseModel

store_router = APIRouter(prefix='/product', dependencies=[Depends(check_permission)])


# 1. 创建知识库
@store_router.post('/product_search')
async def product_search_api(request: ProductSearchRequest):
    log.info(f'/product_search: request:{request}')
    try:
        product_search_response = product_search(request)
        log.info(f'/product_search: response:{product_search_response}')
        return SuccessResponse(data=product_search_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_search, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))


# 2. 产品对比
@store_router.post('/product_compare')
async def product_compare_api(request: ProductCompareRequest):
    log.info(f'/product_compare: request:{request}')
    try:
        product_compare_response = product_compare(request)
        log.info(f'/product_search: response:{product_compare_response}')
        return SuccessResponse(data=product_compare_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_compare, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))


# 3. 全量更新产品特征库
@store_router.post('/update')
async def product_update_api():
    log.info('/product_update')
    try:
        product_update_response = product_update()
        log.info(f'/product_update: response:{product_update_response}')
        return SuccessResponse(data=product_update_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/update, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# # 3. 增量更新产品特征库
# @store_router.post('/increment_update')
# async def product_update_incr_api(request: ProductUpdateIncrRequest):
#     log.info(f'/increment_update: request:{request}')
#     try:
#         response = product_increment_update(request)
#         log.info(f'/increment_update: response:{response}')
#         return SuccessResponse(data=response)
#     except Exception as e:
#         trace_info = traceback.format_exc()
#         log.error(f'Exception for /product/update_incr, e: {e}, trace: {trace_info}')
#         return FailResponse(error=str(e))

# 4. you may ask
@store_router.post('/product_question')
async def product_question_api(request: ProductQuestionRequest):
    log.info(f'/product_question: request:{request}')
    try:
        product_question_response = product_question(request)
        log.info(f'/product_question: response:{product_question_response}')
        return SuccessResponse(data=product_question_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_question, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 5. 发起异步产品检索
@store_router.post('/request_product_search')
async def request_product_search(request: ProductSearchRequest):
    log.info(f'/request_product_search, request: {request}')
    t0 = datetime.now()
    task_id = get_task_id(request)
    log.info(f'/request_product_search costs {datetime.now() - t0}, task_id: {task_id}')
    return SuccessResponse(data=ProductSearchTaskResponse(taskId=task_id))

class TaskRequest(BaseModel):
    taskId: str

# 6. 流式获取产品检索结果summary
@store_router.post('/get_summary_result')
async def get_summary_result(request: Request, task_request: TaskRequest):
    log.info(f'/get_summary_result, request: {request}')
    t0 = datetime.now()
    try:
        async def event_stream():
            buffer = '' # 用于 logging
            cnt = 0
            try:
                async for event in get_summary(task_request.taskId):
                    if await request.is_disconnected():
                        break
                    cnt += 1
                    if cnt == 1:
                        log.info(f'/get_summary_result: first chunk costs {datetime.now() - t0} to arrive.')
                    buffer += event.strip()[len('data: '):]
                    yield event
            finally:
                log.info(f'/get_summary_result, costs {datetime.now() - t0}. task_id: {task_request.taskId}, summary: {buffer}')

        return StreamingResponse(event_stream(), media_type='text/event-stream')
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /get_summary_result, task_id: {task_request.taskId}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 7. 获取产品检索products
@store_router.get('/get_products_result/{task_id}')
async def get_products_result(
    task_id: str,
    max_retries: int = 60,
    retry_delay: int = 3  # 默认 3 秒
):
    log.info(f'/get_products_result, task_id: {task_id}')
    t0 = datetime.now()
    resp = await get_products(task_id, retry_delay * max_retries)
    log.info(f'/get_products_result costs {datetime.now() - t0}, task_id: {task_id}, products: {resp}')
    if resp:
        return SuccessResponse(data=resp)
    else:
        return FailResponse(error='Products data not available after timeout')

async def get_products_result_original(
    task_id: str,
    max_retries: int = 60,
    retry_delay: int = 3  # 默认 3 秒
):
    log.info(f'/get_products_result, task_id: {task_id}')
    t0 = datetime.now()
    retry_count = 0
    while retry_count < max_retries:
        try:
            # 直接调用同步函数（不关心它的耗时）
            products_response = get_products(task_id)
            log.info(f'/get_products_result, task_id: {task_id}, products: {products_response}')

            # 检查 products 是否为空
            if not products_response.products:
                retry_count += 1
                log.warning(f'Products empty, retrying... (Attempt {retry_count}/{max_retries})')
                await asyncio.sleep(retry_delay)  # 关键点：异步 sleep，不阻塞事件循环
                continue
            log.info(f'/get_products_result costs {datetime.now() - t0}')
            return SuccessResponse(data=products_response)

        except Exception as e:
            trace_info = traceback.format_exc()
            log.error(f'Exception for /get_products_result, request: {task_id}, e: {e}, trace: {trace_info}')
            return FailResponse(error=str(e))

    # 重试次数耗尽仍无数据
    log.error(f"Max retries reached for task_id: {task_id}, products still empty.")
    return FailResponse(error="Products data not available after retries")
