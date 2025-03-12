from data.database import TableModel
from sqlalchemy import Column, String, Integer


class SearchEntity(TableModel):
    task_id = Column(String)
    maxNum = Column(Integer)
    messages = Column(String)

class ProductsEntity(TableModel):
    task_id = Column(String)
    products = Column(String)