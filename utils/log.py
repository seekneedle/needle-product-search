from data.database import TableModel, connect_db
from sqlalchemy import Column, Integer, String
import logging
import os
from datetime import datetime
from utils.config import config
from logging.handlers import TimedRotatingFileHandler


# 定义日志模型
class LogEntry(TableModel):
    level = Column(String)
    message = Column(String)


# 自定义日志处理器
class DatabaseLogHandler(logging.Handler):
    def emit(self, record):
        LogEntry.create(
            level=record.levelname,
            message=self.format(record)
        )


# 配置日志记录
def get_log():
    log_path = os.path.join(os.path.dirname(__file__), '..', 'output')
    if not os.path.exists(log_path):
        os.mkdir(log_path)

    level = logging.INFO if config['log_level'] == 'info' else logging.DEBUG
    logger = logging.getLogger()
    logger.setLevel(level)

    log_filename = os.path.join(log_path, 'server.log')

    format_str = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d:%(funcName)s] - %(message)s'

    # 创建一个 TimedRotatingFileHandler，按天滚动日志
    file_handler = TimedRotatingFileHandler(
        filename=log_filename,
        when='midnight',
        interval=1,
        backupCount=21,  # 保留最近 21 天的日志
        encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(format_str))
    logger.addHandler(file_handler)

    # 添加自定义的日志处理器
    db_handler = DatabaseLogHandler()
    db_handler.setLevel(level)
    db_handler.setFormatter(logging.Formatter(format_str))
    logger.addHandler(db_handler)

    return logger


log = get_log()


if __name__ == '__main__':
    connect_db()

    log.info('test')

    for _log in LogEntry.query_all():
        level = _log.level
        message = _log.message
        timestamp = _log.create_time
        print(f'level: {level}, message: {message}, timestamp: {timestamp}')
