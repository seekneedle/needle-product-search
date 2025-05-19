from utils.geo_codes import country_codes, province_codes, city_codes

# 搜索不完整的国家名称
def get_country_code(name):
    if name is None or name == '':
        return ''
    specials = [
        '孟加拉国', '中国', '德国', '法国', '英国',
        '韩国', '泰国', '美国', '梵蒂冈城国',
    ]
    if name.endswith('国') and name not in specials:
        name = name[:-1]

    for c in country_codes.keys():
        if name in c:
            return country_codes[c]
    return ''

def get_province_code(name):
    if name is None or name == '':
        return ''
    if name.endswith('省') or name.endswith('州'):
        name = name[:-1]
    for province, code in province_codes.items():
        if name in province:
            return code
    return ''

# 搜索不完整的城市名称
def get_city_code(name):
    if name is None or name == '':
        return ''
    if name.endswith('市') or name.endswith('县'):
        name = name[:-1]
    # 遍历字典，检查不完整的名称是否是完整名称的一部分
    for city, code in city_codes.items():
        if name in city:
            return code
    return ''

def to_codes(addresses: list):
    countries, provinces, cities = [], [], []
    for addr in addresses:
        c = get_country_code(addr)
        if c != '':
            countries.append(c)
        c = get_province_code(addr)
        if c != '':
            provinces.append(c)
        c = get_city_code(addr)
        if c != '':
            cities.append(c)
    return countries, provinces, cities

if __name__ == '__main__':
    pass