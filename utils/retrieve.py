from pydantic import BaseModel
from typing import Optional
from utils.bailian import create_client
from alibabacloud_bailian20231229 import models as bailian_20231229_models
from alibabacloud_tea_util import models as util_models
from utils.config import config
from typing import Dict, List
import traceback
from utils.log import log
from utils.config import config


class RetrieveRequest(BaseModel):
    ids: List = []
    id: Optional[str] = None
    query: Optional[str] = None
    top_k: Optional[int] = None
    rerank_top_k: Optional[int] = None
    sparse_top_k: Optional[int] = None
    rerank_threshold: Optional[float] = None
    search_filters: Optional[Dict[str, str]] = None
    min_score: Optional[float] = None


class RetrieveNode(BaseModel):
    text: str
    score: float
    metadata: Dict


class RetrieveResponse(BaseModel):
    chunks: Optional[List[RetrieveNode]] = None


def retrieve(query, top_k, id=config['kb_id']):
    """封装retrieve操作为一个独立的函数"""
    client = create_client()
    chunks = []

    try:
        retrieve_request = bailian_20231229_models.RetrieveRequest(
            query=query,
            index_id=id,
            enable_reranking=True,
            dense_similarity_top_k=50,
            rerank_top_n=top_k,
            sparse_similarity_top_k=10,
        )
        runtime = util_models.RuntimeOptions()
        headers = {}
        result = client.retrieve_with_options(config['workspace_id'], retrieve_request, headers, runtime)
        for node in result.body.data.nodes:
            chunks.append(RetrieveNode(score=node.score, text=node.text, metadata=node.metadata))
    except Exception as e:
        trace_info = traceback.format_exc()
        log.error(f'Exception for retrieve query:{query} , e: {e}, trace: {trace_info}')
    return chunks

