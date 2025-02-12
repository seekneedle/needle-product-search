from pydantic import BaseModel
import requests
from typing import List
import json
from utils.config import config
from utils.security import decrypt
from server.response import RequestError

class ProductUpdateResponse(BaseModel):
    result: str

def get_product_nums():
    product_nums = []
    #url = f'https://gatewayqa.uuxlink.com/mcsp/productAi/page'
    url = 'https://mapi.uuxlink.com/mcsp/productAi/page'
    data = requests.get(url).json()['data']
    if data is not None and 'records' in data.keys() and data['records'] is not None:
        for record in data['records']:
            product_nums.append(record['productNum'])
        current = data['current']
        pages = data['pages']
        while current < pages:
            data = requests.get(url, params={'current': current+1}).json()['data']
            if data is not None and 'records' in data.keys() and data['records'] is not None:
                for record in data['records']:
                    product_nums.append(record['productNum'])
                    current = data['current']
                    pages = data['pages']
    return product_nums

def get_product_details(product_nums):
    product_details = []
    return product_details

def product_update():
    product_nums = get_product_nums()

    return ProductUpdateResponse(result="OK")