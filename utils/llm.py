from openai import OpenAI
from utils.security import decrypt
from utils.config import config

client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

def generate(messages):
    completion = client.chat.completions.create(
        model="qwen-plus-2024-09-19",
        messages=messages
    )
    return completion.choices[0].message.content


async def stream_generate(messages):
    completion = client.chat.completions.create(
        model="qwen-plus-2024-09-19",
        messages=messages,
        stream=True,
        stream_options={"include_usage": True}
    )
    for chunk in completion:
        if len(chunk.choices) > 0:
            yield f"data: {chunk.choices[0].delta.content}\n\n"
