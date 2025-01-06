import shutil
import os
from utils.config import config
import hashlib
from pydantic import BaseModel
from typing import Optional


class File(BaseModel):
    name: str
    file_content: bytes


class Document(BaseModel):
    doc_name: str
    doc_id: str
    status: str
    message: Optional[str] = None


def save_file_to_index_path(index_id, filename, content):
    """文件流转成File，保存到index_id命名的文件夹"""
    file_path_root = os.path.join(os.path.dirname('__file__'), config['filestore_root_dir'])
    index_path = os.path.join(file_path_root, index_id)
    if not os.path.exists(index_path):
        os.makedirs(index_path)
    files_path = os.path.join(index_path, filename)
    with open(files_path, 'wb') as file:
        file.write(content)
    return files_path


def delete_file(file_path):
    """  
    删除指定路径的文件  
    """
    try:
        os.remove(file_path)
        print(f'文件 {file_path} 已成功删除。')
    except FileNotFoundError:
        print(f'错误: 文件 {file_path} 不存在。')
    except PermissionError:
        print(f'错误: 没有权限删除文件 {file_path}。')
    except Exception as e:
        print(f'删除文件 {file_path} 时发生错误: {e}')


def delete_directory(dir_path):
    """  
    删除指定路径的文件夹  
    """
    try:
        shutil.rmtree(dir_path)
        print(f'文件夹 {dir_path} 已成功删除。')
    except FileNotFoundError:
        print(f'错误: 文件夹 {dir_path} 不存在。')
    except PermissionError:
        print(f'错误: 没有权限删除文件夹 {dir_path}。')
    except Exception as e:
        print(f'删除文件夹 {dir_path} 时发生错误: {e}')


def calculate_md5(file_path):
    """
    计算文件的 MD5 哈希值
    :param file_path: 文件路径
    :return: 文件的 MD5 哈希值
    """
    # 创建一个 md5 对象
    md5_hash = hashlib.md5()

    try:
        # 以二进制模式打开文件
        with open(file_path, "rb") as file:
            # 分块读取文件内容，防止大文件占用过多内存
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)

        # 返回 MD5 哈希值
        return md5_hash.hexdigest()
    except FileNotFoundError:
        print('文件未找到')
        return None
    except PermissionError:
        print('没有权限访问文件')
        return None
    except Exception as e:
        print(f'发生错误: {e}')
        return None


def read_file(file_path):
    # 读取文件内容
    with open(file_path, 'rb') as file:
        file_content = file.read()
    return file_content


if __name__ == '__main__':
    file_path = 'output/server.log'
    file_content = read_file(file_path)
    print(file_content)
    file_path = save_file_to_index_path('test', 'server.log', file_content)
    print(file_path)
    file_size = os.path.getsize(file_path)
    print(file_size)
