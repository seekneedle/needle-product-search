import requests
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import traceback
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

#
# search_product_kb
# get_dynamic_feature
# get_product_feature
# get_dynamic_features
# get_product_features
# filter_dynamic
#

def search_product_kb(user_input_summary: str, rerank_top_k: int, env: str):
    # user_input_summary = args.input.user_input_summary # 检索字符串（用户需求总结）
    # rerank_top_k = args.input.top_k # 知识库返回最相似片段数量
    # env = args.input.env
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
    if rerank_top_k is not None:
        rerank_top_k = int(rerank_top_k)
        data["rerank_top_k"] = rerank_top_k
        data["top_k"] = rerank_top_k * 2
        data["sparse_top_k"] = rerank_top_k * 2
    response = requests.post(url, headers=headers, json=data)
    product_nums = []
    products = []
    for chunk in response.json()['data']['chunks']:
        metadata = chunk['metadata']
        product_nums.append(metadata['doc_name'])
        products.append({"product_feature": chunk['text'], "product_num": metadata['doc_name']})
    return {"product_nums": product_nums, "products": products}

####

## helper
# def not_null(value):
#     if value is not None and value != "":
#         return True
#     return False

def field_valid(d: dict, key: str) -> bool:
    return key in d and d[key] != ""

def get_field_str(d: dict, key: str) -> str:
    return str(d[key]) if field_valid(d, key) else ''

def get_feature_desc(product_detail, intro, parent_key, keys=None):
    if not product_detail or not parent_key:
        return ""

    try:
        values = []

        if keys is None:
            key_list = parent_key.split(".")
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
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    else:
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    try:
        product_features = [f"productNum：{product_num}"]
        data = requests.get(url).json()['data']
        lines = data["lineList"]
        cals = []
        for line in lines:
            for cal in line["calList"]:
                if cal['isOpen'] == 1:
                    out_cal = {}
                    out_cal["price"] = get_field_str(cal, 'adultSalePrice') # 原为 float 类型
                    out_cal["depart_date"] = cal['departDate']
                    out_cal["back_date"] = cal['calBackDate']
                    out_cal["stock"] = get_field_str(cal, 'stock') # 原为 int 类型
                    cals.append(out_cal)
                    product_features.append(get_feature_desc(cal, "成人售价", 'adultSalePrice'))
                    product_features.append(get_feature_desc(cal, "出发日期", 'departDate'))
                    product_features.append(get_feature_desc(cal, "返回日期", 'calBackDate'))
                    product_features.append(get_feature_desc(cal, "存量", 'stock'))
        product_feature_str = '\n'.join(product_features)
    except Exception:
        return {"cals": []}
    return {"cals": cals, "product_num": product_num, "product_feature": product_feature_str}


####

def get_product_feature(product_num: str, env: str):
    if env == 'prod':
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    else:
        url = f"https://mapi.uuxlink.com/mcsp/productAi/productInfo?productNum={product_num}"
    try:
        product_detail = requests.get(url).json()['data']
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
def batch_features(product_nums: list, env: str, func):
    products = {}
    #
    # todo 并发数量应该多少？
    #
    with ThreadPoolExecutor(max_workers=8) as executor:
        # map<future, to_add_name_list>
        futures = {executor.submit(func, pn, env): pn for pn in product_nums}

        for f in as_completed(futures):
            try:
                feature = f.result()
                prod_num = futures[f]
                products[prod_num] = feature
            except Exception as e:
                trace_info = traceback.format_exc()
                info = f'Exception for batch_features, e:{e}, prod_num:{futures[f]}, trace: {trace_info}'
                print(f'__exception: {info}')
    return {'products': products}

def get_dynamic_features(product_nums: list, env: str):
    # products = { pn : get_dynamic_feature(pn, env) for pn in product_nums }
    return batch_features(product_nums, env, get_dynamic_feature)

def get_product_features(product_nums: list, env: str):
    # products = { pn : get_product_feature(pn, env) for pn in product_nums }
    return batch_features(product_nums, env, get_product_feature)

####


def format_price(price_str):
    """
    将仅包含钱数的字符串转换为保留两位小数的Decimal。
    参数: price_str (str): 包含价格信息的字符串。
    返回: Decimal: 保留两位小数的价格，如果发生异常则返回 None。
    """
    if price_str is None or price_str == '':
        return None
    try:
        # 尝试将字符串转换为 Decimal 类型
        price_decimal = Decimal(price_str)

        # 保留两位小数
        formatted_price = price_decimal.quantize(Decimal('0.00'))

        return formatted_price
    except InvalidOperation:
        # 如果输入不是有效的数字，则捕获异常并返回 None
        print(f"Error: '{price_str}' is not a valid number.")
        return None
    except Exception as e:
        # 捕获其他所有异常
        print(f"An unexpected error occurred: {e}")
        return None

def validate_cal(cal, condition):
    """
    检查旅行产品的团期数据是否符合需求条件。

    参数:
    cal (dict): 旅行产品的团期数据。
    condition (dict): 需求的条件。

    返回: bool: 如果 cal 符合 condition，则返回 True；否则返回 False。
    """
    try:
        # 检查价格是否在范围内
        if field_valid(cal, 'price'):
            min_price = format_price(condition['min_price'])
            max_price = format_price(condition['max_price'])
            price = format_price(cal['price'])
            if min_price is not None and price is not None:
                if min_price > price:
                    return False

            if max_price is not None and price is not None:
                if max_price < price:
                    return False

        # 检查出发日期和返回日期是否与条件中的日期有交集
        if field_valid(cal, 'depart_date') and (field_valid(condition, 'depart_date') or field_valid(condition, 'back_date')):
            # 将字符串日期转换为 datetime 对象
            cal_depart_date = datetime.strptime(cal['depart_date'], "%Y-%m-%d")
            cal_back_date = datetime.strptime(cal['back_date'], "%Y-%m-%d")

            condition_depart_date = datetime.strptime(condition['depart_date'], "%Y-%m-%d") if field_valid(condition, 'depart_date') else None
            condition_back_date = datetime.strptime(condition['back_date'], "%Y-%m-%d") if field_valid(condition, 'back_date') else None

            # 条件出发时间比可选出发时间早超过7天
            if condition_depart_date and condition_depart_date < cal_depart_date:
                return False

            # 条件返回时间比可选出发时间早超过7天
            if condition_back_date and condition_back_date <= cal_depart_date:
                return False

        if field_valid(cal, 'depart_date'):
            cal_depart_date = datetime.strptime(cal['depart_date'], "%Y-%m-%d")
            # 如果 cal_depart_date 比今天早，返回 False
            if cal_depart_date < datetime.today():
                return False

        # 检查存量是否满足最低要求
        if field_valid(condition, 'stock') and field_valid(cal, 'stock'):
            stock_condition = int(condition['stock'])
            stock_cal = int(cal['stock'])
            if stock_cal < stock_condition:
                return False

        if field_valid(cal, 'stock'):
            stock_cal = int(cal['stock'])
            if stock_cal <= 0:
                return False

        # 如果所有条件都满足，则返回 True
        return True
    except ValueError as e:
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        info = traceback.format_exc()
        return False, info

def filter_dynamic(condition, products):
    # condition = args.input.condition
    # products = args.input.products
    product_nums = []
    # print(f'__filter dynamic: products:{products}')
    for pn, product in products.items():
        # print(f'__prodoct:{product}')
        for cal in product['cals']:
            if validate_cal(cal, condition):
                if product['product_num'] not in product_nums:
                    product_nums.append(product['product_num'])
                    break
    return {"product_nums": product_nums}



if __name__ == '__main__':
    env = 'uat'

    user_input_summary = '用户需求：为父母二人带一个 12 岁男孩规划一个新加坡周末两天的旅行产品。'
    rerank_top_k = 5
    kb_res = search_product_kb(user_input_summary, rerank_top_k, env)
    print(kb_res)
    print(json.dumps(kb_res, indent=4))
    print('_' * 40)

    # product_num = 'U167127'
    # ans = get_dynamic_feature(product_num, env)
    # print(ans)
    # print(json.dumps(ans, indent=4))
    # print('_' * 40)

    product_nums = kb_res['product_nums']
    # [
    #     "U182795",
    #     "U176847",
    #     "U174845",
    #     "U181428",
    #     "U184243"
    # ]
    ans = get_dynamic_features(product_nums, env)
    print(ans)
    print(json.dumps(ans, indent=4))
    print('_' * 40)

    ans = get_product_features(product_nums, env)
    print(ans)
    print(json.dumps(ans, indent=4))
    print('_' * 40)
    sys.exit(0)

    from filter_dynamic_test_data import condition, products
    ans = filter_dynamic(condition, products)
    print(ans)
