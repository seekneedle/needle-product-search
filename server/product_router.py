from fastapi import APIRouter, Depends
import traceback

from server.auth import check_permission

from utils.log import log
from services.product_search import product_search, ProductSearchRequest
from services.product_compare import product_compare, ProductCompareRequest
from services.product_update import product_update
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