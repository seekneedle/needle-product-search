from pydantic import BaseModel
from typing import List
from typing import Optional

from data.search import SearchEntityExx
from server.response import RequestError
from utils.config import config
from utils.security import decrypt
from utils import coze_wf
from utils.log import log


class ProductQuestionRequest(BaseModel):
    is_uux: Optional[int] = 0
    messages: List[object]
    class Config:
        arbitrary_types_allowed = True

class ProductQuestionResponse(BaseModel):
    questions: List[object]


async def product_question(request: ProductQuestionRequest):
    log.info(f'/get_question product_question() begins')
    if request.is_uux != 0 or not request.messages:
        parsed_data = {'questions': []}
        response = ProductQuestionResponse(**parsed_data)
        return response

    recent_messages = request.messages[-11:]
    parsed_data = await coze_wf.get_questions(recent_messages)
    return ProductQuestionResponse(**parsed_data)
