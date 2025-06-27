import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))

import multiprocessing
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import traceback

from openai import OpenAI, APIError

from utils.security import decrypt
from utils.config import config
from utils.log import log
from utils import geo

client = OpenAI(
        api_key=decrypt(config['api_key']),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        # timeout=1
    )

def qwen_call(messages, return_type: str, task_id: str, job_name: str, model_name: str):
    # task_id 和 job_name 只用于 logging 目的
    log.info(f'{task_id} {model_name} {job_name} begins')
    t0 = datetime.now()
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={'type': return_type}
        )
        rsp = completion.choices[0].message.content
        log.info(f'{task_id} {model_name} {job_name} done, cost {datetime.now() - t0}, request_id: {completion.id}, usage: {completion.usage}, raw result:_{rsp}_')
        return rsp
    except APIError as e:
        log.info(f'{task_id} {model_name} {job_name} APIError: {e}')
        return ''
    except Exception as e:  # 其他异常（如网络问题）
        log.info(f'{task_id} {model_name} {job_name} api Exception: {str(e)}')
        return ''

# 无 log 的版本。（带大量 log 的版本，见本文件下方）
def qwen_stream_call(messages, queue, model_name: str):
    # task_id 和 job_name 只用于 logging 目的
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,
        stream_options={'include_usage': True} # 得到 token 使用情况统计
    ) # 貌似是第一个 chunk 返回时才返回
    cnt = 0
    last_chunk = None
    for chunk in completion:
        last_chunk = chunk
        # log.info(f'stream raw chunk: {chunk}')
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content is not None: # 真正的回复
            queue.put(f'data: {delta.content}\n\n')
            # log.info(f'qwen_stream_call {model_name} WRAPPER chunk {cnt}: _{delta.content}_')
            cnt += 1
    queue.put(None)
    # 每个 chunk，都含同样的 id
    # 最后一个 chunk，choices 为空列表，usage 包含本次请求所使用的 token 量。
    log.info(f'{model_name} request_id: {last_chunk.id}, usage: {last_chunk.usage}')


# wrapper for qwen_stream_call()
async def stream_generate_ex(messages, task_id: str, job_name: str, model_name: str):
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER before calling qwen')
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=qwen_stream_call, args=(messages, queue, model_name))
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER before process.start()')
    process.start()
    log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER after process.start()')

    try:
        cnt = 0
        while True:
            # 异步监听队列（避免阻塞事件循环）
            data = await asyncio.get_event_loop().run_in_executor(
                None,  # 使用默认线程池
                queue.get  # 阻塞调用，但通过线程池转为异步
            )
            if cnt == 0:
                log.info(f'stream_call {task_id} {model_name} {job_name} WRAPPER first chunk received')
            if data is None: # 结束信号
                break
            # log.info(f'stream_call {model_name} {job_name} WRAPPER chunk {cnt}: _{data.strip()}_')
            cnt += 1
            yield data  # 返回 SSE 数据
    finally:
        process.join()  # 确保进程退出




def to_condition_dates_prompt(recent_messages: list) -> str:
    weekdays_chinese = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
    weekday_num = int(datetime.now().strftime("%w")) # 0（周日）到 6（周六）
    today_str = datetime.now().strftime("%Y年%m月%d日") + weekdays_chinese[weekday_num]

    prompt_condition = f'''
        #背景和需求#
        请根据顾客与旅游行业客服人员的对话，提取出该顾客对出发日期和返回日期的需求。
        两者都有可能是个日期范围，也都有可能是确定的某天。都有可能是精确的，也有可能是模糊的。
        为此，出发日期对应两个字段，depart_date_min 和 depart_date_max，分别是日期范围的下界和上界。
        返回日期也对应两个字段，back_date_min 和 back_date_max，分别是日期范围的下界和上界。
        各日期的提取格式为 yyyy-MM-dd，比如：2025-06-29。

        以下为这段对话，其中 user 为顾客，assistant 为客服人员。

        ======
        {recent_messages}
        ======

        #输出格式#
        提取结果放到 json 对象中，结构化返回。以下为该 json 对象所含字段及其默认值。
        各字段都是字符串类型，格式都是 yyyy-MM-dd，默认值都是空串。
        - depart_date_min
        - depart_date_max
        - back_date_min
        - back_date_max

        #背景知识#
        a. 今天日期为 {today_str}
        c. 2025 年的部分公共假期：
          c.1. 劳动节：5月1日至5日
          c.2. 端午节：5月31日至6月2日
          c.3. 国庆节、中秋节：10月1日至8日。中秋节是10月6日，与国庆假期重合。
          c.4. 寒假：1月15日到2月15日，暑假：7月1日到8月30日，暑期：7月1日到8月30日。
        d. 2026 年的部分公共假期：
          d.1. 元旦：1月1日
          d.2. 春节：2月16日到23日
          d.3. 清明节：4月4日到6日
          d.4. 寒假：1月15日到2月15日，暑假：7月1日到8月30日，暑期：7月1日到8月30日。

        #几个原则#
        1. 只考虑顾客直接提到的出发、返回日期。不要根据出发日期和旅行时长推算返回日期。
        2. 顾客提到的日期，应按“离现在最近的将来的某日期”也就是“即将来到的某日期”这一原则理解。
        3. 类似“本月”、“这个月20号”、“下个月”、“下个月中旬”、“下下个月”、“下周”、“明年”等相对日期，
           应该根据背景知识里提到的今天日期，推算出其指代的具体日期或日期范围。
        4. “五一”是指“五一劳动节假期”这样一个范围，而不是仅“5月1日这一天”。
           “十一”是指“国庆节假期”这样一个范围，而不是“10月1日这一天”。
           类似地，“元旦”、“清明”、“端午”、“中秋”、“国庆”、“春节”等也是指对应的假期日期范围，而不是仅节日当天，
           除非顾客特意明确指出是当天。
        5. 如果顾客只提到了一个日期（范围），但没有明确说它是出发日期还是返回日期，则认为该日期范围
           既是出发日期（范围），也是返回日期（范围）。
        6. 不允许编造内容。必须严格从给定对话内容中提取。
    '''
    return prompt_condition

def to_condition_others_prompt(recent_messages: list) -> str:
    prompt_condition = f'''
        #背景和需求#
        根据顾客与旅游行业客服人员的对话，提取出该顾客对出行人数、出行时长、产品价格的需求。
        不允许编造内容。必须严格从对话内容中提取。

        以下为这段对话，其中 user 为顾客，assistant 为客服人员。

        ======
        {recent_messages}
        ======

        #输出格式#
        提取结果放到 json 对象中，结构化返回。以下为该 json 对象所含字段。
        它们都是整数类型，默认值都是 0。
        - tourists
        - days_min
        - days_max
        - price_min
        - price_max

        #提取顾客的出行人数#
        1. 提取顾客提到的出行人数，放到 tourists 中。
        2. 若顾客提到“家庭游”、“一家人”、“亲子游”等，则至少有三人。
        3. 若顾客没提到人数，或无法判断，则认为至少有一人。不能出现 0 人的情况。

        #提取顾客希望的出行时长#
        1. 若顾客只提到了一个时长，且无法判断是下限还是上限，则同时设置 days_min 和 days_max 为该值。
        2. 若顾客只提及了下限或上限两者之一，则只设置相应变量，另一个设置为默认值 0。
        3. 否则，提取顾客希望的出行时长下限、上限，分别放到 days_min 和 days_max 里。

        #提取顾客希望的价格#
        1. 若顾客只提到了一个价格，且无法判断是下限还是上限，则同时设置 price_min 和 price_max 为该值。
        2. 若顾客只提及了下限或上限两者之一，则只设置相应变量，另一个设置为默认值 0。
        3. 否则，提取顾客希望的价格下限、上限，分别放到 price_min 和 price_max 里。
    '''
    return prompt_condition

def to_addresses_prompt(recent_messages: list) -> str:
    prompt_addresses = f'''
        #背景和需求#
        从顾客与旅游行业客服人员的对话中，解析出顾客想去旅游的目的地各地名，
        包括：国家、省、城市、州、郡、县、道等。
        注意，如果有比国家更高一级的地名，类似“北欧”、“波罗的海国家”、“巴尔干国家”、“东南亚”这样的，必须转换成国家。
        不要包含出发地的地名。

        以下为这段对话，其中 user 为顾客，assistant 为客服人员。

        ======
        {recent_messages}
        ======

        #输出格式#
        提取结果放到 json 对象中，结构化返回。该 json 对象只有一个字段：
        - addresses: 字符串数组类型，它的每个元素都是提取出来的一个地名
    '''
    return prompt_addresses

def to_summary_intention_prompt(recent_messages: list) -> str:
    prompt_user_summary_intention = f'''
        根据用户聊天历史，总结用户对旅行产品的需求，并判断用户的意图。
        结果放到 json 对象中，结构化返回。

        关于用户的需求总结：
        要以用户的口吻输出，不要以客服人员的角度总结。结果放在 input_summary 中。
        如果总结中涉及到已推荐产品，要带上产品编号，但不要带其标题。
        如果不涉及已推荐产品，就不用说"目前没有提到具体推荐的产品编号"这样的话。
        输出文字要平实，不要带文学色彩。要简短，不要啰嗦。

        关于用户的意图：
        1. 如果用户感觉以前系统推荐的产品不太合适、或者不够多，希望再推荐些其他产品，返回 intention = 1。
        2. 如果用户表示出对某个或某几个产品的肯定，或进一步询问已推荐的一个或几个产品的详细信息（如出发日期、价格、特点等），
        或想对比几个已推荐产品的某些特点，返回 intention = 2，并将用户指定的各产品编号放入 product_nums 列表中。
        注意，产品编号的格式是：以字母 U 打头，后跟六位数字。从用户需求中提取产品编号时，要严格根据这个格式判断。
        将产品编号放入 product_nums 列表中时，不要忘了字母 U。
        3. 如果是其他意图，返回 intention = 0。
        4. 不管什么意图，都将识别的理由放在 reason 中。

        用户聊天历史记录为：{recent_messages}
    '''
    return prompt_user_summary_intention

def analyze_user_input(recent_messages: list, task_id: str):
    prompt_addresses = to_addresses_prompt(recent_messages)
    prompt_condition_dates = to_condition_dates_prompt(recent_messages)
    prompt_condition_others = to_condition_others_prompt(recent_messages)
    prompt_user_summary_intention = to_summary_intention_prompt(recent_messages)

    messages_addresses = [{'role': 'user', 'content': prompt_addresses}]
    messages_condition_dates = [{'role': 'user', 'content': prompt_condition_dates}]
    messages_condition_others = [{'role': 'user', 'content': prompt_condition_others}]
    messages_user_summary_intention = [{'role': 'user', 'content': prompt_user_summary_intention}]

    with ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(qwen_call, messages_addresses, 'json_object', task_id, 'addresses', config['model_user_addresses'])
        f2 = executor.submit(qwen_call, messages_condition_dates, 'json_object', task_id, 'condition_dates', config['model_user_condition_dates'])
        f3 = executor.submit(qwen_call, messages_condition_others, 'json_object', task_id, 'condition_others', config['model_user_condition_others'])
        f4 = executor.submit(qwen_call, messages_user_summary_intention, 'json_object', task_id, 'user_summary_intention', config['model_user_summary_intention'])

    try:
        addresses = json.loads(f1.result())
    except Exception as e:
        log.info(f'{type(e).__name__} at analyze_user_input.parse_addrs: {e}, task_id:{task_id}.')
        addresses = {}
    if 'addresses' in addresses and len(addresses['addresses']) > 0:
        c1, c2, c3 = geo.to_codes(addresses['addresses'])
        if len(c1) > 0 or len(c2) > 0 or len(c3) > 0:
            addresses['addr_codes_list'] = [c1, c2, c3]

    try:
        condition_dates = json.loads(f2.result())
    except Exception as e:
        log.info(f'{type(e).__name__} at analyze_user_input.parse_dates: {e}, task_id:{task_id}.')
        condition_dates = {}

    try:
        condition_others = json.loads(f3.result())
    except Exception as e:
        log.info(f'{type(e).__name__} at analyze_user_input.parse_condition_others: {e}, task_id:{task_id}.')
        condition_others = {}
    if 'tourists' not in condition_others or condition_others['tourists'] < 1:
        condition_others['tourists'] = 1 # 以防万一

    try:
        user_summary_intention = json.loads(f4.result())
    except Exception as e:
        log.info(f'{type(e).__name__} at analyze_user_input.parse_user_summary_intention: {e}, task_id:{task_id}.')
        user_summary_intention = {}
    # 意图识别时，如果没正面提到某些产品，可能没有 product_nums 字段。补一个，以防不测。
    if 'product_nums' not in user_summary_intention:
        user_summary_intention['product_nums'] = []

    return condition_dates | condition_others, user_summary_intention | addresses

def to_match_prompt(recent_messages, feature: str) -> list:
        prompt = f'''
            根据顾客与旅游行业客服人员的对话内容，判断给定的产品描述是否满足用户的旅游需求。
            如果顾客的需求里对产品数量有要求（类似“给我推荐10个候选产品”这样的），不用管，只看给定的这一个产品是否满足。
            判断时，不用考虑出发日期、返回时期、旅行天数、旅行晚数、人数、价钱这些条件，而是认为这些条件全都满足。

            结果放到 json 对象中，结构化返回。含如下字段：
            1. matched：布尔类型，表示是否满足需求
            2. reason：字符串类型，表示做出判断的原因

            顾客与客服人员的对话内容：
            ======
            {recent_messages}
            ======

            旅游产品描述如下：
            ======
            {feature}
            ======
        '''
        llm_messages = [{'role': 'user', 'content': prompt}]
        return llm_messages


def check_products_matched(recent_messages, full_features, task_id: str, model_name: str, flag: str):
    if len(full_features) == 0:
        return []

    matched_product_nums = []
    with ThreadPoolExecutor(max_workers=len(full_features)) as executor:
        futures = {executor.submit(
            qwen_call, to_match_prompt(recent_messages, feature),
            'json_object', task_id, f'{pn} {flag} if_matched', model_name
        ): pn for pn, feature in full_features.items()}

        for f in as_completed(futures):
            prod_name = futures[f]
            try:
                if f.result() == '': # 出错，只能跳过，无其他办法
                    log.info(f'{task_id} {model_name} {prod_name} if_matched wrong. skipped.')
                    continue
                res = json.loads(f.result())
                log.info(f'{task_id} {model_name} {prod_name} if_matched result:{res}')
                if res['matched']:
                    matched_product_nums.append(futures[f])
            except Exception as e:
                log.info(f'{type(e).__name__}: {e}, prod_num:{prod_name}.')
    return matched_product_nums

def to_content_prompt(recent_messages, feature: str) -> list:
    # todo 没用到 user_preferred 和 back_filled 属性，也没判断产品是否没有动态特征
    prompt = f'''
        结构化返回，结果放到 json 对象中，其中有且只有两个字段：content 和 score。
        根据产品信息，结合顾客与旅游行业客服人员对话内容中的需求，
        给出该产品的推荐理由（输出到 json 对象的 content 字段）和该产品与用户需求的相似度分数（输出到 json 对象的 score 字段，最高 100 分）。
        注意，已知该产品与用户需求比较相符。所以，归纳推荐理由时，请着重给出亮点。
        即使你认为它不太符合顾客需求，也不要直接说它不合适，而是要用“虽然它不完全匹配，但也比较相关”这样的话术。
        如果顾客的需求里对产品数量有要求（类似“给我提供10个候选产品”这样的），不用管，只为给定的这一个产品归纳推荐理由。
        顾客与客服的对话历史：{recent_messages}
        旅游产品信息：{feature}
    '''
    llm_messages = [{'role': 'user', 'content': prompt}]
    return llm_messages

def get_product_contents(recent_messages, prod_infos, task_id: str, model_name: str):
    if len(prod_infos) == 0:
        return []
    res_contents = []
    with ThreadPoolExecutor(max_workers=len(prod_infos)) as executor:
        futures = {executor.submit(
            qwen_call, to_content_prompt(recent_messages, p['full_feature']),
            'json_object', task_id, f"{p['product_num']} content", model_name
        ): p['product_num'] for p in prod_infos}

        # 大模型在极罕见情况下不返回 score。增加 sum_score, num_scores 及相关逻辑以容错。
        sum_score = 0
        num_scores = 0
        for f in as_completed(futures):
            product_num = futures[f]
            try:
                if f.result() == '': # 出错，只能跳过，无其他办法
                    log.info(f'{task_id} {model_name} {product_num} __content wrong__. skipped.')
                    continue
                res = json.loads(f.result())
                res['product_num'] = product_num
                if 'score' in res:
                    sum_score += res['score']
                    num_scores += 1
                log.info(f'{task_id} {model_name} {product_num} content:{res}')
                res_contents.append(res)
            except Exception as e:
                log.info(f'{type(e).__name__}: {e}, prod_num:{product_num}.')

    # 给没有 score 的产品手工增加 score
    num_contents = len(res_contents)
    if num_scores != num_contents:
        log.info(f'{task_id} {model_name} __content wrong__ {num_contents - num_scores} of {num_contents} products have no score')
        manual_score = 85 if num_scores == 0 else (sum_score // num_scores)
        for c in res_contents:
            if 'score' not in c:
                c['score'] = manual_score
                log.info(f'{task_id} {model_name} {product_num} __content wrong__ manual score: {manual_score}')
    return res_contents

if __name__ == '__main__':
    messages = [{'role': 'user', 'content': '中亚五国旅游，帮我找一个。'}]
    task_id = 'mock_task_id'
    o = analyze_user_input(messages, task_id)
    print(o)
