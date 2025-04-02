from data.database import TableModel
from sqlalchemy import Column, String, Integer


class SearchEntity(TableModel):
    task_id = Column(String)
    maxNum = Column(Integer)
    messages = Column(String)

class ProductsEntity(TableModel):
    task_id = Column(String)
    products = Column(String)


class SearchEntityEx(TableModel):
    task_id = Column(String)
    max_num = Column(Integer)
    messages = Column(String)
    user_input_summary = Column(String)
    condition = Column(String)
    product_infos = Column(String)
    result = Column(String)
    # create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    # modify_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    # PRIMARY KEY (id)
