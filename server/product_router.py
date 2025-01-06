from fastapi import APIRouter, Depends
import traceback

from server.auth import check_permission

from utils.log import log
from services.product_search import product_search, ProductSearchRequest

from server.response import SuccessResponse, FailResponse

store_router = APIRouter(prefix='/product', dependencies=[Depends(check_permission)])


# 1. 创建知识库
@store_router.post('/product_search')
async def vector_store_create(request: ProductSearchRequest):
    try:
        product_search_response = product_search(request)
        return SuccessResponse(data=product_search_response)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for /product/product_search, request: {request}, e: {e}, trace: {trace_info}')
        return FailResponse(error=str(e))