import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))

import requests
# import json

###
# 以下代码来自
# https://www.coze.cn/work_flow?space_id=7402213355257102376&workflow_id=7478322545244094503
# 插件 get_product_feature

# 以下是 coze workflow 里原始的提示词，没有用到，仅供参考。
#
coze_input = '' # 调用 get_product_feature_for_update 返回的 product_feature 结果
coze_prompt ='''
# 角色
    你是一个专业的旅行产品分析员，能够准确地从旅行产品详情中提取出产品特点。

    ## 技能
    ### 技能 1: 分析旅行产品特点
    1. 仔细阅读旅行产品详情。
    2. 根据产品详情，分析并总结出该产品的特点，如适合的人群（年纪较大、小孩儿童、蜜月旅行等）、价格特点（适合要求价格低的客户）、游玩地点特点（适合想在草原玩的客户）、活动类型特点（适合想要参加夏令营的客户等）、是否属于比较轻松的产品（比如每天前往的景点较少，或者基本都有交通工具）。
    3. 假设未来你有可能会向客户推荐该产品，你要用比较简单易于寻找的语言组织下产品特点，方便未来做产品检索。
    4. 你给出的产品特点，最好能够通过知识库向量化后更好的查询到。

    ## 限制:
    - 只分析旅行产品相关内容，拒绝回答与旅行产品无关的话题。
    - 不要罗列产品详情中已经存在的内容， 只总结产品详情中没有的high level的产品特点。

产品详情：
{{input}}
'''



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

def get_product_feature_0(env: str, product_num: str) -> str:
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

        product_feature = '\n'.join(product_features)
    except Exception as e:
        print(f"product detail null: {e}")
        product_feature = ""
    return product_feature


def to_prompt(product_feature: str) -> str:
    prompt = f'''
# 角色
    你是一个专业的旅行产品分析员，能够准确地从旅行产品详情中提取出产品特点。

    ## 技能
    ### 技能 1: 分析旅行产品特点
    1. 仔细阅读旅行产品详情。
    2. 根据产品详情，分析并总结出该产品的特点，如适合的人群（年纪较大、小孩儿童、蜜月旅行等）、价格特点（适合要求价格低的客户）、游玩地点特点（适合想在草原玩的客户）、活动类型特点（适合想要参加夏令营的客户等）、是否属于比较轻松的产品（比如每天前往的景点较少，或者基本都有交通工具）。
    3. 假设未来你有可能会向客户推荐该产品，你要用比较简单易于寻找的语言组织下产品特点，方便未来做产品检索。
    4. 你给出的产品特点，最好能够通过知识库向量化后更好的查询到。

    ## 限制:
    - 只分析旅行产品相关内容，拒绝回答与旅行产品无关的话题。
    - 不要罗列产品详情中已经存在的内容， 只总结产品详情中没有的high level的产品特点。

产品详情如下：
========
{product_feature}
========
'''
    return prompt

####
#### 以上来自 coze workflow
####


from utils.config import config
from utils import llm
def get_product_feature_for_update(product_num: str) -> str:
    # print(f'________env: {config["env"]}')
    product_feature = get_product_feature_0(config['env'], product_num)
    # print(f'________product_feature: type:{type(product_feature)}, content:{product_feature}')

    prompt = to_prompt(product_feature)
    messages = [{'role': 'user', 'content': prompt}]
    llm_feature = llm.qwen_call(messages, 'text', 'mock_task_id', 'update_feature', config['model_update'])
    # print(f'____llm feature, type: {type(llm_feature)}, content: {llm_feature}')
    product_feature = str(product_feature) + '\n产品特征：\n' + llm_feature
    return product_feature

if __name__ == '__main__':
    from utils import coze_wf
    import time
    from datetime import datetime
    product_num_set = [
        'U184684', 'U196979', 'U190311', 'U214838', 'U197714', 'U209495',
        'U187937', 'U178313', 'U189118', 'U170309', 'U168613', 'U167495',
        'U186623', 'U214861', 'U182291', 'U167961', 'U202657', 'U168157',
        'U207928', 'U203481', 'U211838', 'U176808', 'U211903', 'U214472',
        'U171263', 'U200257', 'U214841', 'U167173', 'U204373', 'U178133',
        'U214782', 'U168129', 'U166945', 'U166799', 'U213847', 'U176607',
        'U212463', 'U190339', 'U214744', 'U173666', 'U208182', 'U174392',
        'U212275',
    ]
    for product_num in product_num_set[:10]:
        t0 = datetime.now()
        res_old = coze_wf.get_product_feature(product_num)
        t1 = datetime.now()
        res_new = get_product_feature_for_update(product_num)
        t2 = datetime.now()
        with open(f'update.{product_num}.txt', 'w') as f:
            f.write(f'________old________\n{res_old}\n\n')
            f.write(f'________new________\n{res_new}\n\n')
            f.write(f"old costs: {t1 - t0}\n")
            f.write(f"new costs: {t2 - t1}")
        time.sleep(2)
        print(f'{product_num} done')

