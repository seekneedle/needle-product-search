import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from services import product_update
from utils.log import log
import traceback
from datetime import datetime

#
# 调用方式：在 needle-product-search 顶级目录下，运行
#     python3 tool-update/update-all.py
#

log.info('/product_update_all called')

#
# todo: authentication
#
user_name = input('请输入用户名：')
password = input('请输入密码：')
log.info(f'__user:{user_name}, password:{password}')

try:
    product_update_response = product_update.product_update()
    log.info(f'/product_update_all response:{product_update_response}')
    # return SuccessResponse(data=product_update_response)
except Exception as e:
    trace_info = traceback.format_exc()
    log.error(f'/product_update_all exception: {e}, trace: {trace_info}')
    # return FailResponse(error=str(e))
