import sys
import time
from datetime import datetime

from utils import llm
from utils.log import log

def my_test(query: str):
    request_messages = [
        {
            "role": "user",
            "content": f"您好，{query}，有什么推荐吗？"
        },
    ]
    t00 = datetime.now()
    task_id = 'mock_task_id_1234'
    model_name = 'qwen-turbo'
    log.info(f'__condition_messages:{request_messages}')
    res = llm.analyze_user_input(request_messages, task_id)
    log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
    # log.info(f'/get_task_id {task_id} {model_name}.condition:{res[0]}')
    # log.info(f'/get_task_id {task_id} {model_name}.summary_intention:{res[1]}')

if __name__ == '__main__':
    task_id = 'mock_task_id_1234'

    days = [
        '一周', '一两周', '半个月', '三五天', '十天半个月', '七八天',
        '十几天', '20 天左右', '10天', '3天'
    ]
    # {左右, 大约, 大概}

    dates = [
        '下个月中旬马来西亚深度游',

        '七月份一家三口亲子游',
        '想六月份去欧洲玩',
        '想六七月份去欧洲玩',
        '想七八月份去欧洲玩',
        '想七八月去欧洲玩',
        '想五月去欧洲玩', # wrong
        '六月想去德国玩', # wrong
        '六月去德国玩', # wrong
        '六月想去意大利逛', # correct
        '六月想去法国玩', # wrong
        '想八月去欧洲玩',
        '想七月份去澳大利亚转转',
        '有六月去夏威夷的团吗',
        '六七月份想逛逛夏威夷',
        '六七月份想去夏威夷',

        '想五月出发去欧洲玩',
        '想去欧洲玩，六月去，七月回',
        '想六月份出发去欧洲玩',
        '想六月份去欧洲玩，10号左右去，20号左右回',
        '想去东南亚，5月15日出发',

        '想快速逛一下新加坡，想周二之前走，有合适的吗',
        '想去东南亚，10号之前走', # 有时搞不清楚是几月
        '想五一之前逛一下新加坡',

        '想逛逛新加坡，20号之后吧',
        '希望国庆之后去新加坡逛逛',
        '希望国庆假期之后去新加坡逛逛',

        '想看看泰国，5月10日到20日之间出发',
        '想看看吴哥窟，5月10日到20日之间，有合适的行程吗',

        '想趁今年暑假去欧洲深度游一圈',
        '希望暑假期间去北欧玩',
        '希望寒假期间去北极圈内探险',
        '寒假想去南极看企鹅',

        '想明年春节期间参观一下东南亚风情',
        '想过春节的时候去马代玩玩',

        '我们想元旦去越南玩',
        '我们想元旦假期去看看越南',

        '我们想清明去柬埔寨玩',
        '我们想清明假期去柬埔寨看看',

        '有没有端午假期去东南亚的团',
        '东南亚，想端午去，有合适的吗',

        '想五一去广西桂林',
        '五一假期期间想来个广东全省游',
        '五一期间给安排个出境游呗',
        '有没有劳动节期间去欧洲的团',

        '十一期间能安排埃及金字塔吗',
        '想国庆期间去迪拜逛一圈，有合适的行程吗',

        '有中秋假期的越南短期游吗',
        '中秋假期期间想去新加坡',

        '想圣诞、元旦期间去意大利看看',
        '圣诞节前后，能参观罗马教廷吗',
        '大概圣诞节到元旦期间，能去梵蒂冈吗',

        '这个月想去马来西亚转转',
        '下个月想去马来西亚逛逛',
        '下个月中旬马来西亚深度游',

        '对马来西亚感兴趣，有下周的行程吗',
        '有两周之后出发的马来西亚团吗',

        '有今年开斋节期间的土耳其团吗',
        '开斋节想去土耳其',
        '想体验一下土耳其的斋月风情',

    ]

    prices = [
        '30000', '五千', '30000左右',
        '三万左右', '大概八千吧', '差不多10000', '差不多一万吧，不能再多了',
        '别超过一万二', '最多两万',
        '三万多吧', '三到五万',
        '两三万吧',
        '一万二到两万之间', '30000起',
        '不用考虑', '越少越好', '不封顶', '不是问题', '不差钱'
    ]

    days = [
        '10天',
        '10天左右',
        '大概十天吧',
        '一周',
        '一周左右',
        '大概一周',
        '差不多一周吧',
        '一周差不多吧',
        '大概三五天吧',
        '七八天',
        '十天半个月吧',
        '大概一两周',
        '两周',
        '两周上下',
        '两周左右',
        '半个月',
        '大概十二三天',
        '半个月左右',
        '一周到十天之间',
        '一周到十天左右',
    ]

    # for d in dates:
    #     # query = f'想{d}去新加坡和马来西亚。'
    #     query = d
    #     print(query)
    #     my_test(query)
    #     time.sleep(0.5)

    # for p in prices:
    #     query = f'想去新加坡和马来西亚，父母二人带一个十二岁男孩，预算{p}。'
    #     my_test(query)
    #     time.sleep(1)

    tourists = [
        '一家三口',
        '四五个人',
        '就我自己',
        '就两个人',
        ''
    ]
    i = 0
    for d in dates:
        days_str = days[i % len(days)]
        price_str = prices[i % len(prices)]
        tourists_str = tourists[i % len(tourists)]
        query = f'{d}，{days_str}，{tourists_str}，预算{price_str}'
        my_test(query)
        i += 1
        time.sleep(0.5)
    sys.exit(1)


    # for d in dates:
        # log.info(f'_{d}_')
        # request_messages = [
        #     {
        #         "role": "user",
        #         "content": f"您好，想{d}期间加坡和马来西亚，大概半个月时间，父母二人带一个十二岁男孩。有什么推荐吗"
        #     },
        # ]
        # request_messages = [
        #     {'role': 'user', 'content': '有天山相关的旅游产品吗。想五一期间去，玩一周左右吧。'},
        #     # {"role": "assistant",
        #     #  "content": "编号为U184563的产品“【杏好遇见】双飞8日游”包含天山天池景点，行程中会游览天山天池风景区，体验瑶池仙境。成人售价4980.0元，出发日期2025-04-08，返回日期2025-04-15，目前有6个库存。"},
        #     # {'role': 'user', 'content': '这个感觉不太好。再帮我推荐点别的更合适的吧'},
        # ]

        # request_messages = [
        #     {'role': 'user', 'content': '想要去欧洲度蜜月，大概10天左右'},
        #     {'role': 'assistant','content': '根据用户需求，以下是推荐的产品： 编号为U167001的产品【盈尚·秒杀四国】德国+法国+意大利+瑞士11/12/13天：虽然它不是10天的行程，但其丰富的景点和较为灵活的安排比较相关，适合蜜月旅行。. 编号为U166937的产品【尊悦·王牌四国】一价全含德法意瑞4国13天：这条线路包含了多个著名景点，行程安排较为深入，适合想要在欧洲度过一段浪漫时光的情侣。 编号为U170548的产品【深圳出发】法瑞意德+郁金香一价全含13天：这条线路除了经典的欧洲景点外，还包含了库肯霍夫郁金香公园和哈勒森林风信子等浪漫元素，非常适合蜜月旅行。'},
        #     {'role': 'user', 'content': '哪个适合十一期间的'}
        # ]
        # t00 = datetime.now()
        # model_name = 'qwen-turbo'
        # res = analyze_user_input(request_messages, task_id, model_name)
        # log.info(f'/get_task_id {task_id} {model_name}.analyze_user_input costs {datetime.now() - t00}')
        # log.info(f'/get_task_id {task_id} {model_name}.condition:{res[0]}')
        # log.info(f'/get_task_id {task_id} {model_name}.summary_intention:{res[1]}')
