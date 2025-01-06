from sqlalchemy import create_engine, Column, Integer, String, inspect, DateTime, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import declared_attr
from contextlib import contextmanager
import traceback
from utils.config import config

# 创建一个基类，用于定义表结构
Base = declarative_base()

# 创建数据库引擎和Session
engine = create_engine(config['db_url'], echo=False)
Session = sessionmaker(bind=engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    _session = Session()
    try:
        yield _session
    except Exception as e:
        _session.rollback()
        trace_info = traceback.format_exc()
        print(f'Exception for session_scope, e: {e}, trace: {trace_info}')
    finally:
        _session.close()


# 定义一个通用的数据表类
class TableModel(Base):
    __abstract__ = True

    @declared_attr
    def __tablename__(self):
        return self.__name__.lower()

    id = Column(Integer, primary_key=True, autoincrement=True)
    create_time = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    modify_time = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    def save(self):
        with session_scope() as session:
            if self.id:
                session.merge(self)
                session.commit()
            else:
                session.add(self)
                session.commit()
                session.refresh(self)

    def delete(self):
        with session_scope() as session:
            session.query(self.__class__).filter_by(id=self.id).delete()
            session.commit()

    def set(self, **kwargs):
        for key, value in kwargs.items():
            try:
                setattr(self, key, value)
            except Exception as e:
                trace_info = traceback.format_exc()
                print(f'Exception for set db, e: {e}, trace: {trace_info}')
        self.save()

    @classmethod
    def create(cls, **kwargs):
        instance = cls(**kwargs)
        instance.save()
        return instance

    @classmethod
    def get_or_create(cls, **kwargs):
        instance = cls.query_first(**kwargs)
        if instance is not None:
            return instance
        return cls.create(**kwargs)

    @classmethod
    def query_first(cls, **kwargs):
        with session_scope() as session:
            # 执行查询
            result = session.query(cls).filter_by(**kwargs).first()
            return result

    @classmethod
    def query_all(cls, **kwargs):
        with session_scope() as session:
            # 执行查询
            results = session.query(cls).filter_by(**kwargs).all()
            for result in results:
                yield result


def connect_db():
    Base.metadata.create_all(engine)


if __name__ == '__main__':
    class User(TableModel):
        name = Column(String)

    connect_db()

    user = User.create(name='a')
    print(f'save {user.id}, name = {user.name}')

    user.set(name='b')
    print(f'update {user.id}, name = {user.name}')

    for query_user in User.query_all():
        print(f'query {query_user.id}, name = {query_user.name}')

    get_user = User.query_first(name='b')

    print(f'get {get_user.id}, name = {get_user.name}')

    get_user.set(name='c')

    print(f'update {get_user.id}, name = {get_user.name}')

    for query_user in User.query_all():
        print(f'query {query_user.id}, name = {query_user.name}')

    user1 = User.create(name="new")
    for user in User.query_all():
        user.delete()

    for query_user in User.query_all():
        print(f'after delete {query_user.id}, name = {query_user.name}')
    else:
        print(f"delete all")
