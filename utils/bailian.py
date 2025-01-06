from alibabacloud_bailian20231229.client import Client as bailian20231229Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_bailian20231229 import models as bailian_20231229_models
from utils.security import decrypt
from utils.config import config
from utils.files_utils import save_file_to_index_path, calculate_md5, read_file
import os
from data.task import StoreTaskEntity, FileTaskEntity, TaskStatus
import traceback
import requests


def create_client() -> bailian20231229Client:
    """
    使用AK&SK初始化账号Client
    @return: Client
    @throws Exception
    """
    client_config = open_api_models.Config(
        access_key_id=decrypt(config['ak']),
        access_key_secret=decrypt(config['sk'])
    )
    # Endpoint 请参考 https://api.aliyun.com/product/bailian
    client_config.endpoint = 'bailian.cn-beijing.aliyuncs.com'
    return bailian20231229Client(client_config)


workspace_id = config['workspace_id']
runtime = util_models.RuntimeOptions()
headers = {}
client = create_client()


def create_index(name, chunk_size, overlap_size, separator):
    store_name = name + '_' + config['env']

    # meta_extract_columns_0 = bailian_20231229_models.CreateIndexRequestMetaExtractColumns(
    #     key='file_name',
    #     value='file_name',
    #     type='variable',
    #     desc='文件名',
    #     enable_llm=False,
    #     enable_search=False
    # )

    params = {
        'sink_type': 'DEFAULT',
        'name': store_name,
        'structure_type': 'unstructured',
        'source_type': 'DATA_CENTER_CATEGORY',
        #"meta_extract_columns": [meta_extract_columns_0],
        "category_ids": ["cate_83ac9528cb4b45a58b7b3a54b1039978_10224804"]
    }

    # 动态添加可选参数
    if chunk_size:
        params['chunk_size'] = chunk_size
    if overlap_size:
        params['overlap_size'] = overlap_size
    if separator:
        params['separator'] = separator
    create_index_request = bailian_20231229_models.CreateIndexRequest(
        **params
    )
    result = client.create_index_with_options(workspace_id, create_index_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    index_id = result.body.data.id
    return index_id


def update_index(index_id, file_ids):
    submit_index_job_request = bailian_20231229_models.SubmitIndexAddDocumentsJobRequest(
        index_id=index_id,
        source_type='DATA_CENTER_FILE',
        document_ids=file_ids
    )
    result = client.submit_index_add_documents_job_with_options(workspace_id, submit_index_job_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    job_id = result.body.data.id
    return job_id


def get_index_result(index_id, job_id):
    get_index_job_status_request = bailian_20231229_models.GetIndexJobStatusRequest(
        job_id=job_id,
        index_id=index_id
    )
    result = client.get_index_job_status_with_options(workspace_id, get_index_job_status_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    return result

def add_file_lease(task_id, category_id, file_name, file_content):
    file_name = file_name
    file_path = save_file_to_index_path(task_id, file_name, file_content)
    md_5 = calculate_md5(file_path)
    size_in_bytes = str(os.path.getsize(file_path))
    apply_file_upload_lease_request = bailian_20231229_models.ApplyFileUploadLeaseRequest(
        file_name=file_name,
        md_5=md_5,
        size_in_bytes=size_in_bytes
    )
    result = client.apply_file_upload_lease_with_options(category_id, workspace_id,
                                                         apply_file_upload_lease_request,
                                                         headers,
                                                         runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    lease_id = result.body.data.file_upload_lease_id
    url = result.body.data.param.url
    upload_file_headers = result.body.data.param.headers
    return lease_id, url, upload_file_headers, file_path


def upload_file(file_path, url, upload_file_headers):
    file_content = read_file(file_path)
    response = requests.put(url, data=file_content, headers=upload_file_headers)
    if response.status_code != 200 or not response.ok:
        raise RuntimeError(f'Exception for upload_file: {file_path}, url: {url}, response: {response.status_code}'
                           f' {response.text}')


def add_file(category_id, lease_id):
    add_file_request = bailian_20231229_models.AddFileRequest(
        lease_id=lease_id,
        parser='DASHSCOPE_DOCMIND',
        category_id=category_id
    )
    result = client.add_file_with_options(workspace_id, add_file_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    file_id = result.body.data.file_id
    return file_id


def add_store(task_id, name, chunk_size, overlap_size, separator):
    task = StoreTaskEntity.create(task_id=task_id, status=TaskStatus.RUNNING)
    try:
        index_id = create_index(name, chunk_size, overlap_size, separator)
        task.set(index_id=index_id)
        return task
    except Exception as e:
        trace_info = traceback.format_exc()
        task.set(status=TaskStatus.FAILED,
                 message=f'Exception for add_store, task_id: {task.task_id},  name: {name}, e: {e}, '
                         f'trace: {trace_info}')
        return None


def add_files(task_id, index_id, files):
    category_id = config['parent_category_id']
    task = StoreTaskEntity.get_or_create(task_id=task_id, index_id=index_id)
    task.set(status=TaskStatus.RUNNING)
    if files:
        file_ids = []
        for file in files:
            file_task = FileTaskEntity.create(task_id=task.task_id, status=TaskStatus.RUNNING, doc_name=file.name.split('.')[0])
            try:
                lease_id, url, upload_file_headers, file_path = add_file_lease(task.task_id, category_id,
                                                                               file.name, file.file_content)
                file_task.set(local_path=file_path)
                upload_file(file_path, url, upload_file_headers)
                file_id = add_file(category_id, lease_id)
                file_task.set(doc_id=file_id)
                file_ids.append(file_id)
            except Exception as e:
                trace_info = traceback.format_exc()
                file_task.set(status=TaskStatus.FAILED,
                         message=f'Exception for add_files, task_id: {task.task_id},  id: {task.index_id}, file_name: '
                                 f'{file.name}, e: {e}'
                                 f', trace: {trace_info}')
        try:
            job_id = update_index(task.index_id, file_ids)
            task.set(job_id=job_id)
        except Exception as e:
            trace_info = traceback.format_exc()
            task.set(status=TaskStatus.FAILED,
                     message=f'Exception for add_files, task_id: {task.task_id},  index_id: {index_id}, e: {e}, '
                             f'trace: {trace_info}')
    else:
        task.set(status=TaskStatus.COMPLETED)


def list_file(index_id):
    list_index_documents_request = bailian_20231229_models.ListIndexDocumentsRequest(
        index_id=index_id,
        page_size=999999
    )
    result = client.list_index_documents_with_options(workspace_id, list_index_documents_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    all_files = result.body.data.documents
    return all_files


def delete_store_files(index_id, document_ids):
    delete_index_document_request = bailian_20231229_models.DeleteIndexDocumentRequest(
        index_id=index_id,
        document_ids=document_ids
    )
    result = client.delete_index_document_with_options(workspace_id, delete_index_document_request, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
    deleted_ids = result.body.data.deleted_document
    return deleted_ids


def delete_file(file_id):
    result = client.delete_file_with_options(file_id, workspace_id, headers, runtime)
    if result.status_code != 200 or not result.body.success:
        raise RuntimeError(result.body)
