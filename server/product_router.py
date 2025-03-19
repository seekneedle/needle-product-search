from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import traceback

import time

from server.auth import check_permission

from utils.log import log
from services.product_search import product_search, ProductSearchRequest, ProductSearchTaskResponse, get_summary, ProductsResponse
from services.product_compare import product_compare, ProductCompareRequest
from services.product_update import product_update
from services.product_increment_update import product_increment_update, ProductUpdateIncrRequest
from services.product_question import product_question, ProductQuestionRequest
from server.response import SuccessResponse, FailResponse

store_router = APIRouter(prefix='/product', dependencies=[Depends(check_permission)])


# 1. 创建知识库
@store_router.post('/product_search')
async def product_search_api(request: ProductSearchRequest):
    try:
        product_search_response = product_search(request)
        return SuccessResponse(data=product_search_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_search, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))


# 2. 产品对比
@store_router.post('/product_compare')
async def product_compare_api(request: ProductCompareRequest):
    try:
        product_compare_response = product_compare(request)
        return SuccessResponse(data=product_compare_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_compare, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))


# 3. 全量更新产品特征库
@store_router.post('/update')
async def product_update_api():
    try:
        product_update_response = product_update()
        return SuccessResponse(data=product_update_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/update, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 3. 增量更新产品特征库
@store_router.post('/increment_update')
async def product_update_incr_api(request: ProductUpdateIncrRequest):
    try:
        response = product_increment_update(request)
        return SuccessResponse(data=response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/update_incr, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 4. you may ask
@store_router.post('/product_question')
async def product_question_api(request: ProductQuestionRequest):
    try:
        product_question_response = product_question(request)
        return SuccessResponse(data=product_question_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_question, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 5. 发起异步产品检索
@store_router.post('/request_product_search')
async def request_product_search(request: ProductSearchRequest):
    return SuccessResponse(data=ProductSearchTaskResponse(task_id="aasd323d1-bhgy6x-cz5s6h1"))


# 6. 流式获取产品检索结果summary
@store_router.get('/get_summary_result/{task_id}')
async def get_summary_result(request: Request, task_id: str):
    try:
        async def event_stream():
            async for event in get_summary(task_id):
                if await request.is_disconnected():
                    break
                yield event

        return StreamingResponse(event_stream(), media_type='text/event-stream')
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /vector_store/get_summary_result, task_id: {task_id}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))

# 7. 获取产品检索products
@store_router.get('/get_products_result/{task_id}')
async def get_products_result(task_id: str):
    return SuccessResponse(data=ProductsResponse(products=[{"productNum": "U001",
"score":"94",
"content":"该产品…"
}]))