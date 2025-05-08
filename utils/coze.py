import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))  # 将项目根目录添加到 Python 路径
############# 以上两行在单独测试本文件时加上

import requests
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import traceback
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.log import log

#
# search_product_kb
# get_dynamic_feature
# get_product_feature
# get_dynamic_features
# get_product_features
# filter_dynamic
#

def search_product_kb(user_input_summary: str, rerank_top_k: int, env: str):
    env = 'uat' # 暂时 hard code
    if env == 'prod':
        url = "http://8.152.213.191:8471/vector_store/retrieve"
        id = "icmp3tfyk6"
    else:
        url = "http://8.152.213.191:8475/vector_store/retrieve"
        id = "icmp3tfyk6"
    auth = "Basic bmVlZGxlOm5lZWRsZQ=="

    headers = {
        'Content-Type': 'application/json',
        'Authorization': auth
    }
    data = {
        "id": id,
        "query": user_input_summary,
        "min_score": 0
    }
    data["rerank_top_k"] = rerank_top_k
    data["top_k"] = rerank_top_k * 2
    data["sparse_top_k"] = rerank_top_k * 2
    response = requests.post(url, headers=headers, json=data)
    product_nums = []
    products = []

    try:
        for chunk in response.json()['data']['chunks']:
            metadata = chunk['metadata']
            product_nums.append(metadata['doc_name'])
            products.append({"product_feature": chunk['text'], "product_num": metadata['doc_name']})
        # return {"product_nums": product_nums, "products": products}
    except Exception as e:
        trace_info = traceback.format_exc()
        info = f'Exception for search_product_kb(), e:{e}, trace: {trace_info}'
        log.info(f'__exception: {info}')
    return {"product_nums": product_nums, "products": products}

    # for chunk in response.json()['data']['chunks']:
    #     metadata = chunk['metadata']
    #     product_nums.append(metadata['doc_name'])
    #     products.append({"product_feature": chunk['text'], "product_num": metadata['doc_name']})
    # return {"product_nums": product_nums, "products": products}

####

## helper
# def not_null(value):
#     if value is not None and value != "":
#         return True
#     return False

def field_valid(d: dict, key: str) -> bool:
    return key in d and d[key] != ''

# 只用在生成 dynamic feature
def get_field_str(d: dict, key: str) -> str:
    return str(d[key]) if field_valid(d, key) else ''

# def get_field_int(d: dict, key: str, default_val: int):
#     return d[key] if key in d else default_val

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

def get_dynamic_feature(product_num: str, env: str):
    if env == 'uat':
        url = f'https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}'
    else:
        url = f'https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}'
    try:
        product_features = [f'productNum：{product_num}']
        data = requests.get(url).json()['data']
        if data is None:
            return {}
        lines = data['lineList']
        # log.info(f'____________raw dynamic lines:{lines}')
        out_cals = {'cals' : []}
        out_features = {}
        for line in lines:
            trip_days_str = get_field_str(line, 'tripDays') # 原为 int 类型
            trip_nights_str = get_field_str(line, 'tripNight') # 原为 int 类型
            out_cals['trip_days'] = trip_days_str
            # out_cals['trip_nights'] = trip_nights_str
            cnt = 0
            for cal in line['calList']:
                if cal['isOpen'] == 1:
                    out_cal = {
                        'price' : get_field_str(cal, 'adultSalePrice'), # 原为 float 类型
                        'depart_date' : cal['departDate'],
                        'back_date' : cal['calBackDate'],
                        'stock' : get_field_str(cal, 'stock') # 原为 int 类型
                    }
                    out_cals['cals'].append(out_cal)

                    product_features.append(get_feature_desc(cal, '成人售价', 'adultSalePrice'))
                    product_features.append(get_feature_desc(cal, '出发日期', 'departDate'))
                    product_features.append(get_feature_desc(cal, '返回日期', 'calBackDate'))
                    # product_features.append(get_feature_desc(cal, '旅行天数', 'tripDays'))
                    # product_features.append(get_feature_desc(cal, '旅行夜数', 'tripNight'))
                    product_features.append(get_feature_desc(cal, '存量', 'stock'))

                    out_feature = {
                        '成人售价' : get_field_str(cal, 'adultSalePrice'),
                        '出发日期' : get_field_str(cal, 'departDate'),
                        '返回日期' : get_field_str(cal, 'calBackDate'),
                        '旅行天数' : trip_days_str,
                        # '旅行夜数' : trip_nights_str,
                        '存量' : get_field_str(cal, 'stock'),
                    }
                    cnt += 1
                    out_features[f'线路{cnt}'] = out_feature
        product_feature_str = '\n'.join(product_features)
    except Exception:
        return {}
    return {
        'product_num': product_num,
        'cals': out_cals,                       # 机器用，dict
        'product_feature': product_feature_str, # 人类用，str
        'product_feature_dict' : out_features   # 人类用，dict
    }

####

def get_product_feature(product_num: str, env: str):
    if env == 'prod':
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    else:
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    try:
        product_detail = requests.get(url).json()['data']
        if product_detail is None:
            return {}
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
    return {"product_feature": product_feature_str, "product_num": product_num}


# helper
def batch_features(product_nums: list, env: str, func) -> dict:
    products = {}
    #
    # todo 并发数量应该多少？
    #
    with ThreadPoolExecutor(max_workers=10) as executor:
        # map<future, to_add_name_list>
        futures = {executor.submit(func, pn, env): pn for pn in product_nums}

        for f in as_completed(futures):
            try:
                feature = f.result()
                if feature: # 若不是空 dict
                    prod_num = futures[f]
                    products[prod_num] = feature
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for batch_features, e:{e}, prod_num:{futures[f]}, trace: {trace_info}'
                print(f'__exception: {info}')
    return products

def get_dynamic_features(product_nums: list, env: str):
    # products = { pn : get_dynamic_feature(pn, env) for pn in product_nums }
    return batch_features(product_nums, env, get_dynamic_feature)

def get_product_features(product_nums: list, env: str):
    # products = { pn : get_product_feature(pn, env) for pn in product_nums }
    return batch_features(product_nums, env, get_product_feature)

####

# 将仅包含钱数的字符串转换为保留两位小数的Decimal。
# 参数: price_str (str): condition 和 feature_cal 中的 price 字符串。
# 返回: Decimal: 保留两位小数的价格，如果发生异常则返回 0
def format_price(price_str):
    if price_str is None or price_str == '':
        return 0
    try:
        # # 尝试将字符串转换为 Decimal 类型
        # price_decimal = Decimal(price_str)
        #
        # # 保留两位小数
        # formatted_price = price_decimal.quantize(Decimal('0.00'))

        # 将字符串转换为 Decimal 类型，并保留两位小数
        formatted_price = Decimal(price_str).quantize(Decimal('0.00'))
        return formatted_price
    except InvalidOperation:
        # 如果输入不是有效的数字，则捕获异常并返回 None
        print(f"Error: '{price_str}' is not a valid number.")
        return 0
    except Exception as e:
        # 捕获其他所有异常
        print(f"An unexpected error occurred: {e}")
        return 0

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

def days_matched(cals: dict, condition: dict) -> bool:
    if field_valid(cals, 'trip_days'):
        days_cal = int(cals['trip_days'])
        if days_cal is not None and days_cal > 0:
            cond_days_max = get_field_or_default(condition, 'days_max', 0)
            cond_days_min = get_field_or_default(condition, 'days_min', 0)
            if number_matched(days_cal, cond_days_min, cond_days_max, 'days'):
                return True
    log.info('__dynamic_filter: days failed.')
    return False

def price_matched(cal: dict, condition: dict, cond_tourists: int) -> bool:
    if field_valid(cal, 'price'):
        cal_price = format_price(cal['price'])
        if cal_price is not None and cal_price > 0:
            cal_price *= cond_tourists  # 单价 * 人数
            cond_price_min = get_field_or_default(condition, 'price_min', 0)
            cond_price_max = get_field_or_default(condition, 'price_max', 0)
            if number_matched(cal_price, cond_price_min, cond_price_max, 'price'):
                return True
    log.info(f'__dynamic_filter: price failed.')
    return False

def to_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, '%Y-%m-%d')

def date_matched(cal: dict, condition: dict, what: str) -> bool:
    # what: 'depart_date' or 'back_date'
    if not field_valid(cal, what):
        return True
    cal_date = to_date(cal[what])
    # 如果 cal_depart_date 比今天早，返回 False
    if cal_date < datetime.today():
        log.info(f'__dynamic_filter: {what} earlier than today failed.')
        return False

    cond_depart_min_str = get_field_or_default(condition, f'{what}_min', '')
    cond_depart_max_str = get_field_or_default(condition, f'{what}_max', '')
    if cond_depart_min_str == '' and cond_depart_max_str == '':
        return True
    elif cond_depart_min_str != '' and cond_depart_max_str == '':
        if to_date(cond_depart_min_str) <= cal_date:
            return True
    elif cond_depart_min_str == '' and cond_depart_max_str != '':
        if cal_date <= to_date(cond_depart_max_str):
            return True
    elif cond_depart_min_str == cond_depart_max_str:
        cond_date = to_date(cond_depart_min_str)
        if cond_date - timedelta(days=3) <= cal_date <= cond_date + timedelta(days=3):
            return True
    elif cond_depart_min_str != cond_depart_max_str:
        if to_date(cond_depart_min_str) <= cal_date <= to_date(cond_depart_max_str):
            return True
    log.info(f'__dynamic_filter: {what} failed.')
    return False


# 检查旅行产品的团期数据是否符合需求条件。
def cal_matched(cal, condition):
    # log.info(f'__cal_matched(): type(cal):{type(cal)}, cal:{cal}, condition:{condition}')
    try:
        # 存量、人数
        cond_tourists = get_field_or_default(condition, 'tourists', 1)
        if field_valid(cal, 'stock'):
            stock_cal = int(cal['stock'])
            if stock_cal < cond_tourists:
                log.info(f'__dynamic_filter: stock/tourists failed.')
                return False

        if not price_matched(cal, condition, cond_tourists):
            return False
        if not date_matched(cal, condition, 'depart_date'):
            return False
        if not date_matched(cal, condition, 'back_date'):
            return False
        return True
    except ValueError as e:
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        info = traceback.format_exc()
        return False, info

# 检查旅行产品的团期数据是否符合需求条件。
def cals_matched(cals, condition):
    if 'cals' not in cals or len(cals['cals']) == 0:
        log.info(f'__dynamic_filter: cals empty. failed.')
        # 没有合适的团期了
        return False

    # 旅行时长
    if not days_matched(cals, condition):
        return False

    for cal in cals['cals']:
        if cal_matched(cal, condition):
            log.info(f'__dynamic_filter: matched {cal}')
            return True

    return False


def filter_dynamic(condition: dict, products) -> list:
    product_nums = set()
    # log.info(f'__________filter dynamic: products:{products}')
    for pn, product in products.items():
        # log.info(f'__filter_dynamic(): product.cals:{product["cals"]}')
        if cals_matched(product['cals'], condition):
            product_nums.add(product['product_num'])
    return list(product_nums)


def test_get_feature(product_nums: list):
    import time
    for p in product_nums:
        url = f'https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={p}'
        try:
            data = requests.get(url).json()['data']
            if data is None:
                print(f"{p}")
            else:
                print(f"{p} {data['productTitle']}")
                js = json.dumps(data, ensure_ascii=False, indent=4)
                # with open(f'product_desc_{p}.json', 'w') as f:
                #     f.write(js)
        finally:
            pass
        time.sleep(0.2)


if __name__ == '__main__':
    env = 'uat'

    print(f'will visit Georgia')
    user_input_summary = '我想去格鲁吉亚旅行，目前没有提到具体推荐的产品编号。s'
    rerank_top_k = 80
    r = search_product_kb(user_input_summary, rerank_top_k, env)
    product_num_list = list(set(r['product_nums']))
    print(f'{rerank_top_k} -> {len(product_num_list)}')
    test_get_feature(product_num_list)
    sys.exit(0)


    # cals = {'cals': []}
    # condition = {
    #     'depart_date_min': '2025-05-01',
    #     'depart_date_max': '2025-06-30',
    #     'back_date_min': '2025-05-01',
    #     'back_date_max': '2025-06-30',
    #     'tourists': 1,
    #     'days_min': 5,
    #     'days_max': 10,
    #     'price_min': 0,
    #     'price_max': 30000
    # }

    cals = {
        'cals': [
            {'price': '5999.0', 'depart_date': '2025-05-07', 'back_date': '2025-05-13', 'stock': '2'},
            {'price': '5999.0', 'depart_date': '2025-05-25', 'back_date': '2025-05-31', 'stock': '1'},
            {'price': '5999.0', 'depart_date': '2025-05-09', 'back_date': '2025-05-15', 'stock': '2'},
            {'price': '5999.0', 'depart_date': '2026-05-13', 'back_date': '2026-05-19', 'stock': '4'}
        ],
        'trip_days': '7'
    }
    condition = {
        'depart_date_min': '2025-05-01', 'depart_date_max': '2025-06-30',
        'back_date_min': '2025-05-01', 'back_date_max': '2025-06-30',
        'tourists': 1,
        'days_min': 5, 'days_max': 10,
        'price_min': 0, 'price_max': 30000
    }

    if_matched = cals_matched(cals, condition)
    log.info(f'{if_matched}')
    sys.exit(0)

    # product_nums = ['1', '2', 'U167657']
    # res = get_dynamic_features(product_nums, env)
    # log.info(f'\n\nres: {res}')
    # sys.exit(0)

    # user_input_summary = '想五一期间去澳大利亚和新西兰转转，别太累，别自驾'
    # rerank_top_k = 5
    # kb_res = search_product_kb(user_input_summary, rerank_top_k, env)
    # print(kb_res)
    # print(json.dumps(kb_res, indent=4))
    # print('_' * 40)
    #
    # product_nums = kb_res['product_nums']
    product_nums = [
        "U182795",
        # "U176847",
        # "U174845",
        # "U181428",
        # "U184243"
    ]
    ans = get_dynamic_features(product_nums, env)
    print(ans)
    print(json.dumps(ans, indent=4))
    print('_' * 40)

    ans = get_product_features(product_nums, env)
    print(ans)
    print(json.dumps(ans, indent=4))
    print('_' * 40)
    sys.exit(0)

    # from filter_dynamic_test_data import condition, products
    # ans = filter_dynamic(condition, products)
    # print(ans)
