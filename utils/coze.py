import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))  # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

import requests
from datetime import datetime, timedelta, date
import traceback
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.log import log

def search_product_kb(user_input_summary: str, rerank_top_k: int, env: str):
    env = 'uat' # 暂时 hard code
    if env == 'prod':
        url = 'http://8.152.213.191:8471/vector_store/retrieve'
        id = 'icmp3tfyk6'
    else:
        url = 'http://8.152.213.191:8475/vector_store/retrieve'
        id = 'icmp3tfyk6'
    auth = 'Basic bmVlZGxlOm5lZWRsZQ=='

    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }
    data = {
        'id': id,
        'query': user_input_summary,
        'min_score': 0,
        'rerank_top_k' : rerank_top_k,
        'top_k': rerank_top_k * 2,
        'sparse_top_k': rerank_top_k * 2
    }
    response = requests.post(url, headers=headers, json=data)
    product_num_set = set()
    try:
        for chunk in response.json()['data']['chunks']:
            product_num_set.add(chunk['metadata']['doc_name'])
            # feature 在 chunk['text'] 里，但我们不关心
    except Exception as e:
        info = f'Exception for search_product_kb(), e:{e}, trace:{traceback.format_exc()}'
        log.info(f'__exception: {info}')
    return product_num_set

def product_nums_by_codes(level: str, codes: list, my_company_id: str) -> set:
    if len(codes) == 0:
        return set()
    codes_str = ','.join(codes)
    page_size = 50
    url = f'https://mapi.uuxlink.com/mcsp/productAi/page?{level}={codes_str}&companyId={my_company_id}&saleTerminal=1&size={page_size}&current=1'
    log.info(f'__by_addr url: {url}')
    try:
        records = requests.get(url).json()['data']['records']
        # 返回的产品都是合法的，不用过滤
        return set(r['productNum'] for r in records)
    except Exception as e:
        trace_info = traceback.format_exc()
        log.info(f'__get_features_by_codes {level} exception failed. e:{e}, trace:{trace_info}')
        return set()

def product_nums_by_addresses(addr_codes_list: list, my_company_id: str):
    log.info(f'by addresses: {addr_codes_list}, my_company:{my_company_id}')
    if len(addr_codes_list) == 0:
        return {}, {}
    levels = {
        'passCityCodes' : addr_codes_list[2],
        'destProvinceCodes' : addr_codes_list[1],
        'destCountryCodes' : addr_codes_list[0],
    } # 先从小地方开始。否则可能覆盖不了小地方。
    product_nums = set()
    for level, codes in levels.items():
        if len(codes) != 0:
            res = product_nums_by_codes(level, codes, my_company_id)
            # log.info(f'__{level}:{codes}: {res}')
            if len(res) != 0:
                product_nums.update(res)
    # log.info(f'__nums:{product_nums}')
    return product_nums


####

def field_valid(d: dict, key: str) -> bool:
    return key in d and d[key] != ''

# 只用在生成 dynamic feature
def get_field_str(d: dict, key: str) -> str:
    return str(d[key]) if field_valid(d, key) else ''

def get_field_or_default(d: dict, key: str, default_val):
    return d[key] if key in d else default_val

def get_feature_desc(product_detail, intro, parent_key, keys=None) -> str:
    if not product_detail or not parent_key:
        return ''

    try:
        values = []

        if keys is None:
            key_list = parent_key.split('.')
            current_dict = product_detail

            # Navigate through the dictionary using keys in key_list
            for k in key_list[:-1]:
                current_dict = current_dict.get(k)
                if current_dict is None:
                    return f"{intro}："

            if current_dict is not None:
                last_key = key_list[-1]
                if isinstance(current_dict, list):
                    for child_dict in current_dict:
                        values.append(str(child_dict.get(last_key, "")))
                else:
                    value_str = str(current_dict.get(last_key, ""))
                    values.append(value_str)

        else:
            key_list = parent_key.split(".")
            current_dict = product_detail

            # Navigate through the dictionary using keys in key_list
            for k in key_list:
                current_dict = current_dict.get(k)
                if current_dict is None:
                    return f"{intro}："

            if current_dict is not None:
                if isinstance(current_dict, list):
                    for child_dict in current_dict:
                        child_values = []
                        for key in keys:
                            value = child_dict.get(key, "")
                            if value is not None and str(value) != "null":
                                update_value = str(value).replace("\n", " ")
                                child_values.append(update_value)
                        values.append("、".join(child_values))
                elif isinstance(current_dict, dict):
                    child_values = []
                    for key in keys:
                        value = current_dict.get(key, "")
                        if value is not None and str(value) != "null":
                            update_value = str(value).replace("\n", " ")
                            child_values.append(update_value)
                    values.append("、".join(child_values))

        # Join all values with ", "
        combined_value = "; ".join(values)
        return f"{intro}：{combined_value}"

    except Exception as e:
        print(f"An error occurred: {e}")
        return f"{intro}："

'''
1、剩余库存大于0产品（团期：validStock>0）;
2、未到截团时间的产品（团期：endPreDate>=当日）；
3、自研产品，只允许本公司销售渠道售卖。不允许其他渠道或C端展示（productMode!=2）；
4、产品所属供应商是内部供应商时，在供应商系统投放的产品，不允许本公司下的渠道销售；不允许C端小程序销售（supplierInternalFlag!=1）；
5、售卖状态是启售的产品（openState=1）；
6、产品管理合同有效的产品（contractStatus=1）；
7、产品所属供应商有效的产品（supplierStatus=1）；
8、审核状态是审核通过的产品（auditStatus=2）;
'''

# 以下两个函数仅用于 log 目的
def pf_field_desc(pf: dict, k: str):
    return f'{k}:{pf[k]}' if k in pf else f'{k}:_not_present_'

def product_company_to_str(pf: dict):
    return ', '.join([pf_field_desc(pf, k) for k in [
        'productMode', 'proxyCompanyId', 'supplierInternalFlag', 'supplierCompanyId',
        'openState', 'contractStatus', 'supplierStatus', 'auditStatus',
    ]])
# 以上两个函数仅用于 log 目的

# 参数
# my_company_id: 我的分公司id，前端传来
# pf: 从 db 拿到的 product feature
def is_product_company_valid(my_company_id: str, pf: dict) -> bool:
    if my_company_id == '': # 向后兼容，若前端没传来此参数，则不检查 company 是否合法
        return True
    #
    # 这三个字段值有可能为 null
    #     proxyCompanyId（就是 companyId）, supplierInternalFlag, supplierCompanyId
    #
    # case 1: productMode:2, proxyCompanyId:32, supplierInternalFlag:None, supplierCompanyId:None
    # case 2: productMode:1, proxyCompanyId:37, supplierInternalFlag:1, supplierCompanyId:37
    # case 3: productMode:1, proxyCompanyId:37, supplierInternalFlag:0, supplierCompanyId:None

    if pf['productMode'] == 2: # case 1: 自研产品
        return pf['proxyCompanyId'] == my_company_id
    # else: 外采产品
    if pf['supplierInternalFlag'] == 1: # case 2: 内部分公司
        return pf['supplierCompanyId'] != my_company_id
    else: # case 3: 连内部分公司都不是，纯外部
        return True

def is_product_valid(my_company_id: str, pf: dict) -> bool:
    # log.info(f'__is_product_valid: {product_company_to_str(pf)}')
    return (
        is_product_company_valid(my_company_id, pf) # 3,4
        and pf['openState'] == 1  # 要求 5、售卖状态是启售的产品（openState=1）
        and pf['contractStatus'] == 1   # 6、产品管理合同有效的产品（contractStatus=1）
        and pf['supplierStatus'] == 1 # 7、产品所属供应商有效的产品（supplierStatus=1
        and pf['auditStatus'] == 2 # 8、审核状态是审核通过的产品（auditStatus=2）
    )


def cal_to_str(cal_name: str, cal: dict):
    return cal_name + '：' + '，'.join([k + '：' + v for k, v in cal.items()])

def cals_to_str(product_num: str, cals: dict):
    return f'productNum：{product_num}\n' + '\n'.join([cal_to_str(k, v) for k, v in cals.items()])

def get_dynamic_feature(product_num: str, data: dict, cond: dict):
    # log.info(f'__dynamic_feature: {product_num}, cond:{cond}')
    #
    # tripDays, tripNight 是 line 的属性。（cal 里也有，但值为 null）
    # validStock, endPreDate 是 cal 的属性
    #
    out_cals = {'cals': []}
    out_features = {}
    # log.info(f'_____ line count: {len(data["lineList"])}')
    for line in data['lineList']:
        if not line_days_valid(product_num, line, cond):
            continue
        trip_days_str = get_field_str(line, 'tripDays')  # 原为 int 类型
        trip_nights_str = get_field_str(line, 'tripNight')  # 原为 int 类型
        cnt = 0
        for cal in line['calList']:
            # log.info(f"__cal.isOpen: {cal['isOpen']}")
            if cal['isOpen'] == 1:
                if (cal_stock_valid(product_num, cal, cond)
                        and cal_price_valid(product_num, cal, cond)
                        and cal_date_valid(product_num, 'depart_date', cal, cond)
                        and cal_date_valid(product_num, 'back_date', cal, cond)
                ):
                    out_cal = {
                        'price' : get_field_str(cal, 'adultSalePrice'), # 原为 float 类型
                        'closing_date' : cal['endPreDate'],
                        'depart_date' : cal['departDate'],
                        'back_date' : cal['calBackDate'],
                        'valid_stock' : get_field_str(cal, 'validStock'), # 原为 int 类型
                        'trip_days' : trip_days_str,
                    }
                    out_cals['cals'].append(out_cal)

                    out_feature = {
                        '成人售价': get_field_str(cal, 'adultSalePrice'),
                        '结团日期': get_field_str(cal, 'endPreDate'),
                        '出发日期': get_field_str(cal, 'departDate'),
                        '返回日期': get_field_str(cal, 'calBackDate'),
                        '旅行天数': trip_days_str,
                        # '旅行夜数' : trip_nights_str,
                        '存量': get_field_str(cal, 'validStock'),
                    }
                    cnt += 1
                    out_features[f'团{cnt}'] = out_feature
    if len(out_features) == 0:
        return {}
    dynamic_feature_str = cals_to_str(product_num, out_features)
    # log.info(f'__dynamic str: ____{dynamic_feature_str}____')
    return {
        'product_num': product_num,
        'cals': out_cals,                       # 机器用，dict
        'product_feature_dict' : out_features,  # 人类用，dict
        'product_feature': dynamic_feature_str, # 人类用，str
    }

def get_product_feature(product_num: str, product_detail: dict):
    try:
        product_features = [f"productNum：{product_num}"]
        product_features.append(get_feature_desc(product_detail, "参团游类型", 'productGroupTypeName'))
        product_features.append(get_feature_desc(product_detail, "产品类别", 'productTypeName'))
        product_features.append(get_feature_desc(product_detail, "产品名称", 'productTitle'))
        product_features.append(get_feature_desc(product_detail, "副标题", 'productSubtitle'))
        product_features.append(get_feature_desc(product_detail, "产品主题", 'themes.name'))
        product_features.append(get_feature_desc(product_detail, "目的地", 'dests', ["continentName", "countryName", "destProvinceName", "destCityName"]))
        product_features.append(get_feature_desc(product_detail, "产品标签", 'tags.name'))
        product_features.append(get_feature_desc(product_detail, "业务区域", 'businessAreas'))
        product_features.append(get_feature_desc(product_detail, "出发地国家", 'departureCountryName'))
        product_features.append(get_feature_desc(product_detail, "出发地省份", 'departureProvinceName'))
        product_features.append(get_feature_desc(product_detail, "出发地城市", 'departureCityName'))
        product_features.append(get_feature_desc(product_detail, "儿童年龄标准区间开始值", 'childAgeBegin'))
        product_features.append(get_feature_desc(product_detail, "儿童年龄标准区间结束值", 'childAgeEnd'))
        product_features.append(get_feature_desc(product_detail, "儿童身高标准区间开始值", 'childHeightBegin'))
        product_features.append(get_feature_desc(product_detail, "儿童身高标准区间结束值", 'childHeightEnd'))
        product_features.append(get_feature_desc(product_detail, "儿童价格是否含大交通", 'childHasTraffic'))
        product_features.append(get_feature_desc(product_detail, "儿童价是否含床", 'childHasBed'))
        product_features.append(get_feature_desc(product_detail, "儿童标准说明", 'childRule'))
        product_features.append(get_feature_desc(product_detail, "是否包含保险", 'insuranceIncluded'))
        product_features.append(get_feature_desc(product_detail, "营销标签", 'markets.name'))
        product_features.append(get_feature_desc(product_detail, "保险名称、保险类型（境内外旅游险、航空险等）、保险内容", 'insurance', ["name", "typeName", "content"]))
        try:
            for i, line in enumerate(product_detail["lineList"]):
                product_features.append(f"线路{i+1}基本信息：")
                product_features.append(get_feature_desc(line, "线路名称", 'lineTitle'))
                product_features.append(get_feature_desc(line, "线路简称", 'lineSimpleTitle'))
                product_features.append(get_feature_desc(line, "线路缩写", 'lineSortTitle'))
                product_features.append(get_feature_desc(line, "去程交通", 'goTransportName'))
                product_features.append(get_feature_desc(line, "去程航班（如果去程交通是飞机时，包括航空公司编码、航空公司名称、航班号、启程机场编码、去程机场名称、启程出发时间、到达机场编码、到达机场名称、到达时间、日期差、航班顺序）", 'goAirports', ["airlineCode", "airlineName", "flightNo", "startAirportCode", "startAirportName", "startTime", "arriveAirportCode", "arriveAirportName", "arriveTime", "days", "flightSort"]))
                product_features.append(get_feature_desc(line, "回程交通", 'backTransportName'))
                product_features.append(get_feature_desc(line, "回程航班（如果回程交通是飞机时，包括航空公司编码、航空公司名称、航班号、回程机场编码、回程机场名称、回程出发时间、到达机场编码、到达机场名称、到达时间、日期差、航班顺序）", 'backAirports', ["airlineCode", "airlineName", "flightNo", "startAirportCode", "startAirportName", "startTime", "arriveAirportCode", "arriveAirportName", "arriveTime", "days", "flightSort"]))
                product_features.append(get_feature_desc(line, "行程旅游天数", 'tripDays'))
                product_features.append(get_feature_desc(line, "行程旅游晚数", 'tripNight'))
                product_features.append(get_feature_desc(line, "星级（多个逗号间隔）2-二星及以下；3-三星及同级；4-四星及同级；5-五星及同级；own-自理；-1-无；", 'hotelStarName'))
                product_features.append(get_feature_desc(line, "途径城市", 'passCities', ["continentName", "countryName", "provinceName", "cityName"]))
                product_features.append(get_feature_desc(line, "是否需要签证  0=不需要，1=需要", 'needVisa'))
                product_features.append(get_feature_desc(line, "线路特色", 'lineFeature'))
                product_features.append(get_feature_desc(line, "免签标志1:免签2:面签（如需要签证）", 'visaBasic.visas.freeVisa'))
                product_features.append(get_feature_desc(line, "费用包含", 'costInclude'))
                product_features.append(get_feature_desc(line, "费用不含", 'costExclude'))
                product_features.append(get_feature_desc(line, "预定须知", 'bookRule'))
                product_features.append(get_feature_desc(line, "补充说明", 'otherRule'))
                product_features.append(get_feature_desc(line, "温馨提示", 'tipsContent'))
                product_features.append(get_feature_desc(line, "服务标准", 'serviceStandard'))
                product_features.append(get_feature_desc(line, "购物店（购物店地址、购物店名称、特色商品名称、购物店介绍或说明、购物店补充说明）", 'shops', ["address", "shopName", "shopProduct", "remark", "shopContent"]))
                product_features.append(get_feature_desc(line, "自费项目（地址、项目名称和内容、自费项目介绍或说明）", 'selfCosts', ["address", "name", "remark"]))
                product_features.append(get_feature_desc(line, "自费项目说明", 'selfCostContent'))

                try:
                    for i, trip in enumerate(line["trips"]):
                        product_features.append(get_feature_desc(trip, "行程第几天", 'tripDay'))
                        product_features.append(get_feature_desc(trip, "行程内容描述", 'content'))
                        product_features.append(get_feature_desc(trip, "是否含早餐 0 不含 1 含", 'breakfast'))
                        product_features.append(get_feature_desc(trip, "是否含午餐 0 不含 1 含", 'lunch'))
                        product_features.append(get_feature_desc(trip, "是否含晚餐 0 不含 1 含", 'dinner'))
                        product_features.append(get_feature_desc(trip, "当天行程-交通信息（出发地、出发时间、目的地、到达时间、交通类型，bus-大巴；minibus-中巴；train-火车；ship-轮船；liner-游轮；airplane-飞机；99-其他；、）", 'scheduleTraffics', ["departure", "departureTime", "destination", "arrivalTime", "trafficType"]))
                        product_features.append(get_feature_desc(trip, "酒店信息（酒店名称、星级 1 一星 2 两星 3 三星 4 四星 5 五星）", 'hotels', ["name", "star"]))
                        product_features.append(get_feature_desc(trip, "景点信息（景点名称、景点介绍或描述）", 'scenics', ["name", "description"]))
                        product_features.append(get_feature_desc(trip, "行程主题", 'title'))

                except Exception as e:
                    product_features.append("未找到行程信息")
        except Exception as e:
            product_features.append("未找到线路信息")

        product_feature_str = '\n'.join(product_features)
    except Exception as e:
        print(f"product detail null: {e}")
        product_feature_str = ""
    return product_feature_str
    # return {"product_feature": product_feature_str, "product_num": product_num}


# 返回 dynamic feature 和 product_feature
def get_full_feature(product_num: str, my_company_id: str, cond: dict, env: str, flag: str):
    # log.info(f'__get_full_feature {flag} {product_num} begins')
    if env == 'uat':
        url = f'https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}'
    else:
        url = f'https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}'
    try:
        data = requests.get(url).json()['data']
        if data is None:
            log.info(f'__get_full_feature {flag} {product_num} json empty failed')
            return {}, {}
        if not is_product_valid(my_company_id, data):
            log.info(f'__get_full_feature {flag} {product_num} product invalid failed')
            return {}, {}

        df = get_dynamic_feature(product_num, data, cond)
        # log.info(f'___df:_{df}_')
        if len(df) == 0:
            return {}, {}
        pf = get_product_feature(product_num, data)
        # log.info(f'___pf:_{pf}_')
        # log.info(f'__get_full_feature {flag} {product_num} done')
        return df, pf
    except Exception as e:
        trace_info = traceback.format_exc()
        log.info(f'__get_full_feature {flag} {product_num} exception failed. e:{e}, trace:{trace_info}')
        return {}, {}

# helper
def batch_features(product_nums: set, my_company_id: str, cond: dict, env: str, flag: str, func) -> dict:
    dynas, prods = {}, {}

    #
    # todo 并发数量应该多少？
    #
    with ThreadPoolExecutor(max_workers=15) as executor:
        # map<future, to_add_name_list>
        futures = {executor.submit(func, pn, my_company_id, cond, env, flag): pn for pn in product_nums}

        for f in as_completed(futures):
            prod_num = futures[f]
            try:
                df, pf = f.result()
                if len(df) != 0: # 若不是空 dict
                    dynas[prod_num] = df
                    prods[prod_num] = pf
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for batch_features {prod_num}, e:{e}, trace: {trace_info}'
                log.info(f'__exception: {info}')
    return dynas, prods

def get_full_features(product_num_set: set, my_company_id: str, cond: dict, env: str, flag: str):
    log.info(f'__get_full_features {flag} product_nums:{len(product_num_set)}:{product_num_set}, my_company_id:{my_company_id}, condition:{cond}')
    return batch_features(product_num_set, my_company_id, cond, env, flag, get_full_feature)



####

#
# 0 0: 都未指定，直接返回 true
# a 0: 只指定了 min
# 0 b: 只指定了 max
# a b: 指定了 min 和 max
# a a: a 左右。上下浮动 3 天 或 20% 价钱。
#
def number_matched(cal_val, cond_val_min, cond_val_max, what) -> bool:
    if cond_val_max == 0 and cond_val_min == 0:
        return True
    elif cond_val_max == 0 and cond_val_min > 0:
        if cond_val_min <= cal_val:
            return True
    elif cond_val_max > 0 and cond_val_min == 0:
        if cond_val_max >= cal_val:
            return True
    elif cond_val_max == cond_val_min:
        if ((what == 'days' and cond_val_min - 3 <= cal_val <= cond_val_max + 3)
                or (what == 'price' and cond_val_min * 0.8 <= cal_val <= cond_val_max * 1.2)):
            return True
    else: # cond_days_max != cond_days_min
        if cond_val_min <= cal_val <= cond_val_max:
            return True
    return False

def line_days_valid(product_num: str, line: dict, condition: dict) -> bool:
    line_key = 'tripDays'
    if line_key in line and line[line_key] is not None:
        line_days = line[line_key]
        # log.info(f'__line.days: {line_days}')
        cond_days_max = get_field_or_default(condition, 'days_max', 0)
        cond_days_min = get_field_or_default(condition, 'days_min', 0)
        if number_matched(line_days, cond_days_min, cond_days_max, 'days'):
            return True
    # log.info(f'__dynamic_filter {product_num} days failed.')
    return False

def cal_stock_valid(product_num: str, cal: dict, condition: dict):
    # 存量、人数
    cal_key = 'validStock'
    cond_key = 'tourists'
    if cal_key in cal and cal[cal_key] is not None:
        cal_valid_stock = cal[cal_key]
        cond_tourists = get_field_or_default(condition, cond_key, 1)
        if cal_valid_stock >= cond_tourists:
                return True
    # log.info(f'__dynamic_filter: stock/tourists failed.')
    return False

def cal_price_valid(product_num: str, cal: dict, condition: dict) -> bool:
    # 共有这些字段
    #   adultSalePrice, adultRealSalePrice, adultSetPrice
    #   childSalePrice, childRealSalePrice, childSetPrice
    #   dfcSalePrice, dfcSetPrice
    # 含义
    #   sale price: 建议零售价
    #   real sale price: 实际零售价
    #   set price: 结算价
    #   dfc: 单房差，已废弃
    # 判断时用 real sale price

    cal_key = 'adultRealSalePrice'
    if cal_key in cal and cal[cal_key] is not None:
        cal_price = cal[cal_key]
        # log.info(f'__cal.price: {cal_price}')
        cal_price *= get_field_or_default(condition, 'tourists', 1) # 单价 * 人数
        cond_price_min = get_field_or_default(condition, 'price_min', 0)
        cond_price_max = get_field_or_default(condition, 'price_max', 0)
        if number_matched(cal_price, cond_price_min, cond_price_max, 'price'):
            return True
    # log.info(f'__dynamic_filter: {product_num} price failed.')
    return False

def to_date(date_str: str) -> date:
    return datetime.strptime(date_str, '%Y-%m-%d').date()

def cal_date_valid(product_num: str, cond_key: str, cal: dict, condition: dict) -> bool:
    # cond_key: 'depart_date' or 'back_date'
    cal_key = {'depart_date' : 'departDate', 'back_date' : 'calBackDate'}[cond_key]
    cal_closing_key = 'endPreDate'
    if cal_key not in cal or cal_closing_key not in cal:
        return False
    cal_date = to_date(cal[cal_key])
    cal_closing_date = to_date(cal[cal_closing_key])
    date_today = date.today()
    # log.info(f'__cal {cond_key}: {cal_date}, 结团日期: {cal_closing_date}, today: {date_today}')
    if cal_date is None or cal_date == '' or cal_closing_date is None or cal_closing_date == '':
        return False

    # 主要应满足两个判断条件
    #   today <= cal.结团日期 < cal.出发日期 < cal.返回日期
    #   cond.depart_min - 3 <= cal.出发日期 <= cond.depart_max + 3 (返回日期类似）

    # 如果 cal.结团日期 比 today 早，返回 False
    if date_today > cal_closing_date or date_today >= cal_date:
        # log.info(f'__dynamic_filter: {cond_key} cal closing_date/{cond_key} in the past. failed.')
        return False

    cond_min_str = get_field_or_default(condition, f'{cond_key}_min', '')
    cond_max_str = get_field_or_default(condition, f'{cond_key}_max', '')
    if cond_min_str == '' and cond_max_str == '':
        return True
    elif cond_min_str != '' and cond_max_str == '':
        if to_date(cond_min_str) <= cal_date:
            return True
    elif cond_min_str == '' and cond_max_str != '':
        if cal_date <= to_date(cond_max_str):
            return True
    elif cond_min_str == cond_max_str:
        cond_date = to_date(cond_min_str)
        if cond_date - timedelta(days=3) <= cal_date <= cond_date + timedelta(days=3):
            return True
    elif cond_min_str != cond_max_str:
        if to_date(cond_min_str) <= cal_date <= to_date(cond_max_str):
            return True
    # log.info(f'__dynamic_filter: {cond_key} failed.')
    return False


if __name__ == '__main__':
    env = 'uat'
    # product_num_list = ['U178329', 'U173527', 'U176764', 'U175263', 'U178181', 'U170495']
    # product_num_list = {'U170562', 'U166875', 'U166668'}
    product_num_set = {'U166668', 'U179321', 'U166679', 'U179026', 'U184511', 'U171142', 'U179474', 'U168302', 'U173301', 'U167600', 'U170101', 'U166875', 'U180935', 'U200400', 'U166698'}

    my_company_id = ''
    # condition = {
    #     'tourists': 1,
    #     'days_min': 5,
    #     'days_max': 15,
    #     'price_min': 0,
    #     'price_max': 30000,
    #     'depart_date_min': '2025-05-01',
    #     'depart_date_max': '2025-07-30',
    #     'back_date_min': '2025-05-01',
    #     'back_date_max': '2025-07-30',
    # }
    condition = {}
    dynas, prods = get_full_features(product_num_set, my_company_id, condition, env, 'test')
    for p in prods:
        with open(f'prod_feature_{p}.json', 'w') as f:
            f.write(prods[p])
    # print(f'_dynas:{dynas}')
    # print(f'_prods:{prods}')
    sys.exit(0)