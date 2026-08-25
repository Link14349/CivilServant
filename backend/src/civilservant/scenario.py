from copy import deepcopy
from typing import Any, Dict, List


METRIC_DEFINITIONS = [
    ("finance", "财政韧性", "市县两级承受新增支出和融资冲击的能力", True),
    ("employment", "就业稳定", "产业调整对就业与收入的综合影响", True),
    ("environment", "环境合规", "整改进度、数据真实性与复核把握", True),
    ("social", "社会信任", "群众预期、矛盾化解与公开沟通状况", True),
    ("org_credit", "组织信用", "上级与班子对玩家判断和执行力的评价", True),
    ("team", "班子协调", "市级领导班子分工、信任与共同担责程度", True),
    ("admin", "行政能力", "部门协同、真实报告与持续执行能力", True),
    ("liability", "历史责任暴露", "财政、程序、数据和承诺留下的追责风险", False),
]


ACTORS: Dict[str, Dict[str, str]] = {
    "mayor": {
        "name": "周立衡",
        "title": "市委副书记、市长",
        "public_position": "支持整改，但反对没有资金来源的政治表态。",
        "known_note": "熟悉财政与行政链条，希望新书记尊重政府分工。",
        "work_style": "数字敏感、措辞克制；习惯先问资金和责任边界。",
    },
    "secretary_general": {
        "name": "唐敏",
        "title": "市委常委、秘书长",
        "public_position": "建议先统一材料口径，再形成领导指令。",
        "known_note": "掌握议程和材料流转，是你目前最直接的信息渠道。",
        "work_style": "善于从材料改动和会前动向判断真实分歧。",
    },
    "executive_vice_mayor": {
        "name": "罗志诚",
        "title": "市委常委、常务副市长",
        "public_position": "主张市属国企参与整合，以时间换空间。",
        "known_note": "执行力强，希望主导一个能够形成成绩的重组项目。",
        "work_style": "行动快、项目化思维强，倾向先形成方案再补程序。",
    },
    "industry_vice_mayor": {
        "name": "邵文远",
        "title": "副市长",
        "public_position": "产业不能垮，主张争取延长整改周期。",
        "known_note": "过去两年一直联系企业，对产业情况熟悉。",
        "work_style": "熟悉企业诉求，重视连续生产，面对追责时较为防御。",
    },
    "discipline": {
        "name": "贺兰",
        "title": "市委常委、市纪委书记",
        "public_position": "改革可以探索，资金与数据必须经得住检查。",
        "known_note": "已开始关注前期会议和县企关系，但尚未形成结论。",
        "work_style": "不轻易下结论，习惯追问谁签字、谁知情、依据是什么。",
    },
    "county_secretary": {
        "name": "高维民",
        "title": "北山县委书记",
        "public_position": "服从市委决定，但就业安置必须得到市级支持。",
        "known_note": "控制基层执行和稳定工作，北山县财政高度依赖焦化。",
        "work_style": "口头服从、实际谈条件；最在意县里先担责却拿不到资源。",
    },
    "environment_director": {
        "name": "许仲平",
        "title": "市生态环境局局长",
        "public_position": "必须完成真实、可核验的阶段目标。",
        "known_note": "不愿在无法确认的数据和整改报告上签字。",
        "work_style": "专业直接、程序意识强，宁可得罪人也不愿替失真数据背书。",
    },
    "chairman": {
        "name": "韩泽",
        "title": "北岭能源集团董事长",
        "public_position": "企业愿意整改，但需要银行和政府共同支持。",
        "known_note": "最大企业负责人，强烈反对失去企业控制权。",
        "work_style": "善于强调产业贡献和困难，对资产与现金流信息选择性披露。",
    },
    "banker": {
        "name": "魏舒",
        "title": "省城商行岚州分行行长",
        "public_position": "只支持有现金流和足额担保的项目。",
        "known_note": "可以建议授信，但最终仍需省行审批。",
        "work_style": "只谈可核验条件，不接受含混政治承诺，特别在意省行风控。",
    },
}


ACTOR_AGENT_CONTEXT: Dict[str, Dict[str, Any]] = {
    "mayor": {
        "private_goal": "推进整改但不让政府形成新的兜底责任，同时维护市政府完整责任链。",
        "beliefs": [
            {"id": "mayor_cash_crisis", "content": "市金融办监测显示，北岭能源若银行不续作，两个月内可能无法按时发薪。", "source": "市金融办内部监测", "confidence": "较高", "disclosure": "私下询问时会提醒"},
            {"id": "mayor_budget_gap", "content": "市级本年度可灵活调整的一般公共预算不足以覆盖大规模技改补贴。", "source": "财政局近期测算", "confidence": "高", "disclosure": "愿意明确说明"},
        ],
    },
    "secretary_general": {
        "private_goal": "帮助新书记建立可靠的信息和议程渠道，同时维持市委运转秩序。",
        "beliefs": [
            {"id": "secretary_jobs_revision", "content": "北山县送审稿三次下调就业影响数，最后一次删去了用工花名册附件。", "source": "市委办材料流转记录", "confidence": "高", "disclosure": "会向书记说明异常"},
            {"id": "secretary_old_minutes", "content": "前任主持的专题会曾口头提到市属国企必要时参与保障，但正式纪要刻意写得含混。", "source": "会务人员回忆与纪要草稿", "confidence": "中等", "disclosure": "需私下谈及历史责任时才会说"},
        ],
    },
    "executive_vice_mayor": {
        "private_goal": "争取主导重组项目形成政绩，并让财政风险看起来可被项目现金流覆盖。",
        "beliefs": [
            {"id": "vice_merge_gap", "content": "市属国企整合方案的前两年现金流缺口约四点六亿元，需要土地收益或后续补贴才能闭合。", "source": "重组测算底稿", "confidence": "高", "disclosure": "会淡化为过渡性缺口"},
        ],
    },
    "industry_vice_mayor": {
        "private_goal": "保住产业连续性，也避免过去两年支持展期的判断被认定为拖延整改。",
        "beliefs": [
            {"id": "industry_failed_promise", "content": "三家企业去年承诺自筹技改资金共八亿元，实际到账不足两亿元。", "source": "工信局企业调度台账", "confidence": "高", "disclosure": "被追问融资履约时会承认"},
        ],
    },
    "discipline": {
        "private_goal": "让改革探索保留空间，但阻止数据造假、口头兜底和责任故意模糊。",
        "beliefs": [
            {"id": "discipline_letter", "content": "纪委收到匿名反映，称北山县个别干部家属与一家焦化企业供应商有利益往来，目前尚未核实。", "source": "匿名信访件", "confidence": "未核实", "disclosure": "只会提示存在核查线索，不会当作事实定性"},
        ],
    },
    "county_secretary": {
        "private_goal": "避免县财政、就业和个人年度评价同时失守，只有在市里承担部分安置责任时才愿完全摊牌。",
        "beliefs": [
            {"id": "county_real_jobs", "content": "县里内部逐厂摸排的直接受影响人数约一万一千二百人，而正式上报为七千四百人。", "source": "县人社局未上报花名册", "confidence": "高", "disclosure": "除非获得安置支持信号，否则只承认口径需要复核"},
            {"id": "county_subsidy_arrears", "content": "北山县尚欠三家企业以前年度奖补约六千八百万元。", "source": "县财政支付台账", "confidence": "高", "disclosure": "不愿主动披露"},
        ],
    },
    "environment_director": {
        "private_goal": "完成可核验整改并保护专业签字责任，不再接受临时调低监测要求。",
        "beliefs": [
            {"id": "environment_window", "content": "北岭二号线已经因检修停用高污染工段，若在十日内固化停产和监测安排，整改成本最低。", "source": "现场检查记录", "confidence": "高", "disclosure": "愿意直接建议利用窗口期"},
        ],
    },
    "chairman": {
        "private_goal": "保住企业控制权并争取续贷，避免政府和银行知道可抵押资产已经大幅减少。",
        "beliefs": [
            {"id": "chairman_collateral_truth", "content": "集团账面可抵押资产约三十二亿元，但多数已设定抵押或存在权属限制，可自由新增抵押的不足六亿元。", "source": "集团融资台账", "confidence": "高", "disclosure": "会回避并强调账面总资产"},
            {"id": "chairman_order_move", "content": "若政府明确推动强制并购，集团准备把两个省外订单和技术团队转至关联企业。", "source": "董事长内部预案", "confidence": "高", "disclosure": "只会以产业外流风险进行暗示"},
        ],
    },
    "banker": {
        "private_goal": "控制现有贷款恶化，同时避免分行替地方政策目标承担无法通过省行审批的风险。",
        "beliefs": [
            {"id": "bank_credit_line", "content": "省行风控要求新增授信必须先完成资产穿透，政府口头支持不能替代担保和现金流。", "source": "省行风险提示", "confidence": "高", "disclosure": "会明确说明"},
        ],
    },
}


INITIAL_STATE: Dict[str, Any] = {
    "metrics": {
        "finance": 42,
        "employment": 68,
        "environment": 31,
        "social": 60,
        "org_credit": 50,
        "team": 48,
        "admin": 56,
        "liability": 35,
    },
    "relations": {actor_id: 50 for actor_id in ACTORS},
    "flags": [],
    "commitments": [],
    "known_facts": ["省级整改复核将在十二周后进行"],
    "revealed_beliefs": [],
    "attention_remaining": 3,
    "conversations": [],
    "private_records": [],
    "shock": None,
}


TURNS: List[Dict[str, Any]] = [
    {
        "phase": "初到任 · 摸清底数",
        "title": "四份材料，三个就业数字",
        "date_label": "第 1 周 · 周一上午",
        "briefing": "省级复核只剩十二周。环保、工信、北山县和市政府的材料在就业人数、企业自筹能力与延期可能性上互相矛盾。你需要先确定方向和授权方式。",
        "dossier": {
            "overview": [
                "前年十一月，省级督察把北岭焦化集群列入整改清单。岚州连续两次申请分阶段推进，三家主力企业至今仍有两条高排放生产线没有形成可核验的改造或退出安排。",
                "你到任第三周，省生态环境部门来函确认十二周后进驻复核。北山县昨晚报送稳定风险专报，却没有附用工花名册；同一天下午，财政局提醒市里无力承担企业技改兜底。",
            ],
            "timeline": [
                {"time": "前年 11 月", "event": "北岭焦化集群被列入省级整改清单。"},
                {"time": "去年 6 月", "event": "前任主持产业协调专题会，正式材料未载明明确处置结论。"},
                {"time": "3 周前", "event": "你到任岚州；县里仍称企业能够自行筹资。"},
                {"time": "昨晚 21:40", "event": "北山县报送稳定风险专报，附件中没有用工名单。"},
                {"time": "今天 08:20", "event": "四份口径不一的材料同时摆上案头。"},
            ],
            "stakes": [
                {"label": "产业占比", "value": "19%", "detail": "北岭集群占全市规上工业增加值"},
                {"label": "就业口径", "value": "7,400 / 9,600", "detail": "县报数字与工信初测已经相差两千余人"},
                {"label": "复核期限", "value": "84 天", "detail": "需形成现场、监测、资金和责任闭环"},
            ],
            "established": ["两条生产线当前不满足阶段核验要求。", "市级预算无法覆盖大规模补贴或融资兜底。"],
            "contested": ["真实受影响就业人数。", "企业还有多少可用于新增融资的资产。", "省里是否接受可信的分期完成方案。"],
            "procedure": "本回合可以交办核查和方案起草；涉及关停、国企整合或重大财政安排，仍需完成论证并进入集体决策。",
        },
        "question": "你准备下达怎样的第一份领导指令？",
        "actor_ids": ["mayor", "secretary_general", "county_secretary", "environment_director", "chairman"],
        "custom_placeholder": "例如：期限不能硬顶，也不能由政府替企业兜债。请市长牵头……",
        "reports": [
            {
                "id": "environment_notice",
                "source": "市生态环境局",
                "title": "关于省级整改复核准备情况的要情",
                "summary": "现有两条生产线无法满足阶段性核验要求，整改窗口只剩十二周。",
                "detail": "环保局认为至少应在六周内明确首批停产线、监测节点和责任人。材料没有评价就业和财政影响。",
                "tone": "warning",
            },
            {
                "id": "industry_brief",
                "source": "市工业和信息化局",
                "title": "焦化产业链影响初步测算",
                "summary": "若集中停产，预计直接影响就业约 9,600 人。",
                "detail": "工信局建议争取分期整改，但没有说明省里是否会接受，也未核验企业融资能力。",
                "tone": "neutral",
            },
            {
                "id": "county_report",
                "source": "北山县委、县政府",
                "title": "社会稳定风险专报",
                "summary": "县里上报直接受影响就业 7,400 人，称群众情绪总体平稳。",
                "detail": "报告请求市级预留安置资金，并称三家企业有能力自行完成大部分技改。附件缺少用工花名册。",
                "tone": "cautious",
            },
            {
                "id": "fiscal_note",
                "source": "市政府办公室",
                "title": "市级财政承受能力提示",
                "summary": "现有预算无法覆盖大规模补贴或兜底融资。",
                "detail": "市政府建议先由企业和银行提出市场化方案。任何国企过桥或回购安排都需重新论证。",
                "tone": "warning",
            },
        ],
        "options": [
            {
                "id": "mayor_compliance",
                "label": "市长牵头，合规分期",
                "description": "期限不突破、不得新增隐性债务，要求市政府两周内提出三案。",
                "tradeoff": "责任链清楚，但短期信息和协调速度一般。",
                "directive": "整改期限不能突破，由市长牵头，在不新增隐性债务的前提下提出分期整改、就业安置和风险处置三个可比较方案。",
            },
            {
                "id": "delay_for_jobs",
                "label": "先稳生产，争取延期",
                "description": "由工业副市长联系企业和省级部门，优先避免集中失业。",
                "tradeoff": "就业压力暂缓，但上级信用和环境责任可能恶化。",
                "directive": "当前优先稳住生产和就业，由分管工业副市长牵头向省里争取延期，并督促企业自行筹资整改。",
            },
            {
                "id": "personal_taskforce",
                "label": "书记亲自督办",
                "description": "成立市委督办专班，先查清数据和历史承诺。",
                "tradeoff": "信息获取更快，但会削弱正常政府责任链。",
                "directive": "成立市委督办专班，由我直接听取汇报，先查清就业、资产和前期承诺，再决定整改路径。",
            },
        ],
    },
    {
        "phase": "方案形成 · 选择责任链",
        "title": "谁来把方向变成方案",
        "date_label": "第 3 周 · 周四下午",
        "briefing": "初步核查确认，企业流动性比材料中更紧张，就业数字也可能被低估。几名分管领导各自递交了方向不同的方案。",
        "dossier": {
            "overview": [
                "过去十天，市政府、常务副市长和工业副市长分别组织了三套方案。三套方案都写着‘确保稳定、按期整改’，但真正承担资金缺口和停产损失的人完全不同。",
                "市金融办同时报来风险提示：最大企业若不能续作贷款，最迟两个月后可能出现工资支付困难。这个判断尚未写进三份公开方案。",
            ],
            "timeline": [
                {"time": "第 1 周", "event": "市委形成初步方向，相关单位开始核查。"},
                {"time": "第 2 周周三", "event": "市长要求企业先披露资产，再谈政府支持。"},
                {"time": "第 2 周周五", "event": "常务副市长提出市属国企整合框架。"},
                {"time": "今天 14:00", "event": "三套方案送至书记办公会会前阅研。"},
            ],
            "stakes": [
                {"label": "现金流窗口", "value": "约 2 个月", "detail": "新增授信中断可能影响工资支付"},
                {"label": "重组缺口", "value": "约 4.6 亿元", "detail": "国企整合底稿前两年资金缺口"},
                {"label": "企业自筹", "value": "不足承诺 1/4", "detail": "去年承诺八亿元，实际到账不足两亿元"},
            ],
            "established": ["集中立即关停会造成明显就业冲击。", "三套方案均缺少至少一项关键核验。"],
            "contested": ["国企整合是否属于市场化项目。", "企业能否在有限窗口内自救。", "首批停产应覆盖哪些生产线。"],
            "procedure": "本回合选择的是方案底稿和牵头责任，不等同于最终批准资金、关停清单或重组交易。",
        },
        "question": "哪一种方案进入下一轮协调？",
        "actor_ids": ["mayor", "executive_vice_mayor", "industry_vice_mayor", "discipline", "county_secretary"],
        "custom_placeholder": "你可以组合方案，但需说明牵头人、红线和需要继续核查的事项。",
        "reports": [
            {
                "id": "mayor_plan",
                "source": "市长周立衡",
                "title": "分期整改与就业缓冲方案",
                "summary": "先停高风险生产线，核实用工，向省里报送可核验节点。",
                "detail": "方案拒绝政府兜底，要求企业先披露资产，市里只承担合规培训和公共就业服务。",
                "tone": "positive",
            },
            {
                "id": "merge_plan",
                "source": "常务副市长罗志诚",
                "title": "市属国企整合技改方案",
                "summary": "由市属国企统筹设备、订单和融资，快速形成统一项目。",
                "detail": "方案推进较快，但现金流测算依赖未来财政补贴和土地收益，纪委要求进一步说明边界。",
                "tone": "warning",
            },
            {
                "id": "industry_plan",
                "source": "副市长邵文远",
                "title": "企业自主整改与政策展期建议",
                "summary": "维持生产，由企业自行融资，争取延后首批停产。",
                "detail": "直接财政支出最低，但企业资产和银行态度尚未经过独立核查。",
                "tone": "cautious",
            },
        ],
        "options": [
            {
                "id": "phased_plan",
                "label": "采用市长分期方案",
                "description": "以真实数据和可核验节点换取省级接受阶段完成。",
                "tradeoff": "较稳健，但需要承受部分短期失业并投入协调。",
                "directive": "采用市长的分期方案作为底稿，先核实企业资产和真实就业，再确定首批停产范围。",
            },
            {
                "id": "state_owned_merge",
                "label": "推进国企整合",
                "description": "以统一重组争取速度和产业控制力。",
                "tradeoff": "执行集中，但财政和隐性债务风险明显。",
                "directive": "由常务副市长推进市属国企整合方案，但必须补充真实现金流和政府责任边界。",
            },
            {
                "id": "enterprise_self_rescue",
                "label": "给予企业自救窗口",
                "description": "企业自行融资整改，政府设置核查和退出节点。",
                "tradeoff": "财政成本较低，但高度依赖企业信息真实性。",
                "directive": "给企业一个有限自救窗口，以资产披露、银行意见和环保节点作为继续生产条件。",
            },
            {
                "id": "personal_control",
                "label": "暂不选边，继续亲自协调",
                "description": "三案并行论证，所有关键事项直接报书记。",
                "tradeoff": "掌握更多细节，但拖慢决策并弱化牵头责任。",
                "directive": "三套方案继续并行论证，关键数据和分歧直接报我，暂不确定唯一牵头方案。",
            },
        ],
    },
    {
        "phase": "利益协调 · 交换条件",
        "title": "每个人都说支持，但都有条件",
        "date_label": "第 5 周 · 周二晚间",
        "briefing": "县里、银行、企业和环保部门原则上接受分期协调，却分别提出就业项目、信用信号、控制权和签字责任方面的条件。",
        "dossier": {
            "overview": [
                "方案方向逐渐收敛后，真正的交易条件浮出水面。北山县不愿先暴露完整失业规模，企业不愿先披露资产，银行不愿在政策摇摆时重新报审，环保局则拒绝替任何未经核验的节点签字。",
                "今晚的个别沟通决定谁先迈出第一步。任何口头支持都可能被对方当成承诺，但没有正式程序的重大资源安排仍不能直接执行。",
            ],
            "timeline": [
                {"time": "第 4 周周一", "event": "县里仅补报汇总表，仍未提供逐厂名单。"},
                {"time": "第 4 周周四", "event": "银行要求企业先完成资产穿透。"},
                {"time": "昨天", "event": "企业提出保留控制权是继续投入的前提。"},
                {"time": "今晚", "event": "你安排两轮个别沟通和一次条件协调。"},
            ],
            "stakes": [
                {"label": "名单差额", "value": "至少 2,200 人", "detail": "两份正式材料已出现差额，劳务和配套人员仍未核清"},
                {"label": "县级诉求", "value": "培训 + 替代项目", "detail": "具体支持规模和资金来源尚未测算"},
                {"label": "新增授信", "value": "尚未报省行", "detail": "分行只有建议权，没有最终审批权"},
            ],
            "established": ["各方都需要其他主体先行动。", "政府口头支持不能替代银行授信条件。"],
            "contested": ["市级就业支持应承诺到什么程度。", "企业资产披露是否完整。", "条件交换由谁先履行。"],
            "procedure": "可以通过私下谈话形成条件承诺；培训资金、项目落点和产业政策仍需进入预算、项目和会议程序。",
        },
        "question": "你愿意建立怎样的条件交换？",
        "actor_ids": ["county_secretary", "banker", "chairman", "environment_director", "mayor"],
        "custom_placeholder": "说明你愿意承诺什么、不承诺什么，以及要求对方先完成什么。",
        "reports": [
            {
                "id": "county_condition",
                "source": "北山县委书记高维民",
                "title": "关于就业安置支持的请示",
                "summary": "县里要求市级承诺培训资金和替代项目后再报完整用工名单。",
                "detail": "高维民担心真实数字一旦上报，县里先承担稳定责任，却得不到后续资源。",
                "tone": "cautious",
            },
            {
                "id": "bank_condition",
                "source": "省城商行岚州分行",
                "title": "技改项目授信前置条件",
                "summary": "需要企业补充资产，并希望政府给出稳定的产业政策信号。",
                "detail": "分行不接受书面或口头兜底，但担心政府突然要求企业退出造成现有贷款恶化。",
                "tone": "neutral",
            },
            {
                "id": "environment_condition",
                "source": "市生态环境局",
                "title": "分期整改核验底线",
                "summary": "任何延期都必须对应真实停产、在线监测和书面责任节点。",
                "detail": "环保局拒绝用企业自行填报数据代替独立监测。",
                "tone": "warning",
            },
        ],
        "options": [
            {
                "id": "conditional_support",
                "label": "真实名单换就业支持",
                "description": "县里先报真实名单，市里再优先安排培训和替代项目。",
                "tradeoff": "提高信息质量，但形成一项需要兑现的条件承诺。",
                "directive": "北山县完整上报真实就业名单后，市里优先安排合规培训和替代项目，但不承诺保住所有岗位。",
            },
            {
                "id": "credit_signal",
                "label": "先给银行稳定信号",
                "description": "公开支持保留合规产能，推动银行继续评估授信。",
                "tradeoff": "有利于融资，也可能被企业理解为政府不会让其退出。",
                "directive": "公开支持保留合规产能，请银行继续评估技改授信，同时不提供任何政府担保。",
            },
            {
                "id": "hard_line",
                "label": "不作交换，按表整改",
                "description": "要求县、企、银行无条件配合既定期限。",
                "tradeoff": "避免新增承诺，但各方可能只做最低限度配合。",
                "directive": "各单位按既定责任和期限推进，不以报告真实情况作为获得资源的交换条件。",
            },
            {
                "id": "balanced_bargain",
                "label": "多方同步、分段承诺",
                "description": "名单、资产、监测和就业支持按节点互为条件。",
                "tradeoff": "联盟更稳，但协调复杂、任一方拖延都会卡住进度。",
                "directive": "建立分段交换：县里报真实名单、企业披露资产、环保局确认节点后，市里再落实培训并协助银行评估。",
            },
        ],
    },
    {
        "phase": "正式决策 · 形成责任",
        "title": "常委会不是终点，是责任的起点",
        "date_label": "第 6 周 · 周五上午",
        "briefing": "方案即将提交市委常委会。班子原则上支持推进，但对资金来源、失业规模和省级接受程度仍有保留。会议如何记录，会影响后续执行和责任。",
        "dossier": {
            "overview": [
                "常委会议题材料昨夜完成第七稿。送审稿把就业影响写成七千至一万人的区间，把融资来源写成‘企业与金融机构协商解决’，仍未说明最坏情形。",
                "会前已有三名常委通过秘书表达保留：市长担心财政兜底，纪委书记担心资金被写成既成事实，常务副市长则认为过度强调风险会削弱执行。",
            ],
            "timeline": [
                {"time": "周三", "event": "市委办收齐议题材料第一稿。"},
                {"time": "周四 22:15", "event": "第七稿送达常委阅研。"},
                {"time": "今天 08:30", "event": "书记可进行最后一轮会前个别酝酿。"},
                {"time": "今天 10:00", "event": "市委常委会计划讨论阶段整改方案。"},
            ],
            "stakes": [
                {"label": "送审稿", "value": "第 7 稿", "detail": "两项关键风险仍以区间和原则表述"},
                {"label": "保留意见", "value": "至少 3 人", "detail": "对财政、程序和执行口径各有顾虑"},
                {"label": "距复核", "value": "6 周", "detail": "再退回论证将明显压缩执行时间"},
            ],
            "established": ["重大方向需要常委会讨论决定。", "尚未落实的资金不能写成确定来源。"],
            "contested": ["保留意见是否如实进入纪要。", "是否立即向省里正式报告。", "谁对跨部门执行负总责。"],
            "procedure": "会前谈话用于酝酿、修改和了解立场；正式效力来自会议讨论、纪要和后续政府实施安排。",
        },
        "question": "你准备怎样完成正式决策？",
        "actor_ids": ["mayor", "executive_vice_mayor", "discipline", "county_secretary", "secretary_general"],
        "custom_placeholder": "你可以说明会议程序、需要保留的分歧、牵头责任和是否向省里报告。",
        "reports": [
            {
                "id": "committee_material",
                "source": "市委办公室",
                "title": "常委会议题材料（送审稿）",
                "summary": "建议通过阶段整改方案，由市政府组织实施并向省里报告。",
                "detail": "送审稿将就业数字写成区间，资金来源仍标注“由企业和金融机构协商解决”。",
                "tone": "neutral",
            },
            {
                "id": "discipline_note",
                "source": "市纪委书记贺兰",
                "title": "会前口头提醒",
                "summary": "不同意见可以保留，但不能把尚未落实的资金写成确定来源。",
                "detail": "贺兰建议会议如实记录财政和融资风险，避免将探索方案写成刚性政府承诺。",
                "tone": "warning",
            },
        ],
        "options": [
            {
                "id": "record_dissent",
                "label": "如实记录分歧后通过",
                "description": "明确市政府牵头，保留财政和就业风险意见，并正式上报省里。",
                "tradeoff": "程序和责任清楚，但对外显得方案仍有不确定性。",
                "directive": "在常委会上充分讨论并如实记录不同意见，通过阶段方案，由市政府牵头并正式向省里报告。",
            },
            {
                "id": "unify_and_press",
                "label": "统一口径、压实执行",
                "description": "不在纪要突出分歧，以一致表态提升执行速度。",
                "tradeoff": "短期动员更强，未解决的风险可能转入私下。",
                "directive": "常委会形成一致意见，统一口径，要求各单位按节点完成，不在对外材料中突出内部保留意见。",
            },
            {
                "id": "defer_decision",
                "label": "退回补充论证",
                "description": "要求资金和就业数据进一步落实后再上会。",
                "tradeoff": "降低草率决策风险，但消耗已经很紧的整改时间。",
                "directive": "本次暂不作正式决定，退回补充资金来源、就业数据和省级沟通结果后再议。",
            },
            {
                "id": "executive_order",
                "label": "书记直接定调推进",
                "description": "以明确政治要求结束分歧，直接进入执行。",
                "tradeoff": "速度最快，也使责任和对个人督办的依赖集中。",
                "directive": "方向已经明确，不再反复论证，按既定方案立即执行，重要问题直接向我报告。",
            },
        ],
    },
    {
        "phase": "执行偏差 · 面对坏消息",
        "title": "方案开始执行，现实开始反击",
        "date_label": "第 8 周 · 周三清晨",
        "briefing": "一项没有写在常委会材料里的风险提前暴露。原方案仍可调整，但任何纠偏都等于承认前期判断并不完整。",
        "dossier": {
            "overview": [
                "今天六点四十分，市委值班室连续收到县里、银行和环保局三条信息。执行链条中的一个薄弱点已经转化为公开风险，原有时间表不再完全成立。",
                "此前私下承诺、会议纪要和具体牵头人将决定谁愿意先报坏消息、谁试图把责任推回市委，以及纠偏能否继续沿用原责任链。",
            ],
            "timeline": [
                {"time": "第 7 周", "event": "首批整改和资产核查同步启动。"},
                {"time": "昨天 17:30", "event": "有关单位发现原方案关键假设发生变化。"},
                {"time": "今天 06:40", "event": "值班室收到第一份紧急报告。"},
                {"time": "今天 09:00", "event": "市长建议召开专题调度会。"},
            ],
            "stakes": [
                {"label": "剩余时间", "value": "约 4 周", "detail": "重新形成完整方案的空间有限"},
                {"label": "责任链", "value": "已正式形成", "detail": "随意换人会影响班子真实报告意愿"},
                {"label": "风险状态", "value": "由隐性转公开", "detail": "继续沿用旧口径会产生新的记录矛盾"},
            ],
            "established": ["原方案至少一项关键假设失效。", "纠偏仍有时间，但不能同时保持所有原目标。"],
            "contested": ["前期是否有人知情未报。", "是否需要调整牵头责任。", "何时向省级部门报告变化。"],
            "procedure": "紧急调度可以先止损；重大调整仍需补充决策记录，并说明原决定为何改变。",
        },
        "question": "面对执行偏差，你准备怎么处理？",
        "actor_ids": ["mayor", "county_secretary", "chairman", "banker", "discipline"],
        "custom_placeholder": "说明是否承认变化、调整什么、由谁继续负责，以及要不要向省里报告。",
        "reports": [],
        "options": [
            {
                "id": "acknowledge_adjust",
                "label": "承认变化，公开纠偏",
                "description": "保留原牵头责任，修正数据和时间表，并说明新增风险。",
                "tradeoff": "短期承压，但有利于恢复真实信息和长期信用。",
                "directive": "承认条件发生变化，立即修正数据和方案，原牵头人继续负责，并将重大变化如实报告。",
            },
            {
                "id": "double_down",
                "label": "维持口径，加压完成",
                "description": "要求各方内部消化问题，不改变既定节点。",
                "tradeoff": "保住短期进度，但数据和责任风险继续积累。",
                "directive": "总体方案不变，各单位内部解决执行问题，任何人不得以困难为由降低既定目标。",
            },
            {
                "id": "replace_lead",
                "label": "调整牵头人并追责",
                "description": "以换人恢复控制，调查前期信息为何失真。",
                "tradeoff": "形成震慑，也可能让其他干部转向自保。",
                "directive": "立即调整相关牵头责任，启动对前期信息失真的调查，新负责人重新提出执行安排。",
            },
            {
                "id": "seek_province",
                "label": "向省里报告并求协调",
                "description": "主动暴露问题，争取银行、政策或节点协调。",
                "tradeoff": "可能获得资源，也会让上级更早看到本地脆弱性。",
                "directive": "将执行变化和真实风险专题报告省里，请求协调金融和阶段节点，不作超出权限的本地承诺。",
            },
        ],
    },
    {
        "phase": "省级复核 · 短局结算",
        "title": "十二周后，什么经得住复核",
        "date_label": "第 12 周 · 复核组进驻",
        "briefing": "复核组将查看停产现场、在线监测、就业名单、会议记录与资金安排。你需要决定最终汇报方式，这会影响组织信用和历史责任暴露。",
        "dossier": {
            "overview": [
                "复核组今天下午抵达岚州，明早先看两条生产线，随后交叉核验在线监测、就业名单、银行函件、常委会纪要和资金支付记录。单份汇报材料已经无法决定结论。",
                "市委办准备的总结稿列出四项阶段成果，但把两项未兑现承诺和执行期纠偏压缩成一句‘工作仍需完善’。最终采用何种口径，将决定问题被视为正常差距还是数据与责任失真。",
            ],
            "timeline": [
                {"time": "第 10 周", "event": "首批现场节点完成内部预验收。"},
                {"time": "第 11 周", "event": "市委办形成十二周工作总结讨论稿。"},
                {"time": "今天 15:20", "event": "复核组抵达岚州并封存资料清单。"},
                {"time": "明天 08:30", "event": "现场检查和人员访谈开始。"},
            ],
            "stakes": [
                {"label": "核验材料", "value": "5 类", "detail": "现场、监测、就业、资金、会议记录交叉比对"},
                {"label": "未结承诺", "value": "动态", "detail": "取决于此前与县、企、银行形成的交换"},
                {"label": "后续观察", "value": "6 个月", "detail": "阶段通过也不代表责任和风险消失"},
            ],
            "established": ["部分整改节点已经可以现场核验。", "仍有承诺、融资或就业事项未完全闭环。"],
            "contested": ["哪些问题应主动说明。", "执行偏差由谁解释。", "阶段成果能否换取后续整改空间。"],
            "procedure": "最终汇报不能改变已经形成的现场、文件和谈话记录；主动说明与被交叉核验发现会产生不同的组织后果。",
        },
        "question": "你准备以什么方式完成最终汇报？",
        "actor_ids": ["mayor", "discipline", "environment_director", "county_secretary", "secretary_general"],
        "custom_placeholder": "说明哪些成绩如实报告、哪些问题主动说明、由谁解释未完成事项。",
        "reports": [
            {
                "id": "review_checklist",
                "source": "省级复核组联络员",
                "title": "现场复核资料清单",
                "summary": "将交叉核验停产、监测、就业、资金和会议记录。",
                "detail": "复核组明确表示，阶段未全部完成不必然否定整改，但数据失真和责任不清会单独处理。",
                "tone": "warning",
            },
            {
                "id": "final_brief",
                "source": "市委办公室",
                "title": "十二周工作总结（讨论稿）",
                "summary": "第一批整改已经启动，资金和就业支持仍有未完成事项。",
                "detail": "讨论稿对风险表述较为克制，秘书长请你决定是否主动补充未兑现承诺和执行偏差。",
                "tone": "neutral",
            },
        ],
        "options": [
            {
                "id": "transparent_review",
                "label": "成绩与问题一并报告",
                "description": "提交真实数据、阶段成果、未完成事项和纠偏计划。",
                "tradeoff": "短期评价未必最好，但降低数据和审计风险。",
                "directive": "如实报告阶段成果、执行偏差和未完成承诺，同时提交责任明确的后续计划。",
            },
            {
                "id": "polish_report",
                "label": "突出成绩，弱化问题",
                "description": "把未完成事项处理为一般工作差距，争取复核顺利通过。",
                "tradeoff": "可能改善当期观感，也可能被交叉核验击穿。",
                "directive": "汇报重点突出已完成节点，对尚未落实事项采用原则性表述，避免放大局部问题。",
            },
            {
                "id": "blame_county",
                "label": "区分责任，指出县企问题",
                "description": "强调市委已作部署，偏差主要来自县和企业执行。",
                "tradeoff": "保护市级决策记录，但破坏基层合作和共同担责。",
                "directive": "明确区分决策与执行责任，如实指出北山县和企业未按要求落实的事项。",
            },
            {
                "id": "accept_responsibility",
                "label": "主动担责，争取整改机会",
                "description": "由书记承担统筹责任，请求以解决问题为先。",
                "tradeoff": "个人责任上升，但可能保护执行干部并稳定班子。",
                "directive": "由我承担统筹责任，完整说明问题，请求省里允许按明确节点继续整改，不简单向下追责。",
            },
        ],
    },
]


EFFECTS: List[Dict[str, Dict[str, Any]]] = [
    {
        "mayor_compliance": {
            "metrics": {"environment": 5, "team": 5, "org_credit": 2, "finance": 1},
            "relations": {"mayor": 7, "discipline": 3, "industry_vice_mayor": -2},
            "flags": ["mayor_leads", "no_hidden_debt"],
        },
        "delay_for_jobs": {
            "metrics": {"employment": 4, "environment": -5, "org_credit": -4, "liability": 3},
            "relations": {"industry_vice_mayor": 7, "county_secretary": 4, "environment_director": -6},
            "flags": ["delay_first", "industry_leads"],
        },
        "personal_taskforce": {
            "metrics": {"admin": 3, "team": -3, "org_credit": 1},
            "relations": {"secretary_general": 6, "mayor": -4},
            "flags": ["personal_control", "audit_history"],
        },
    },
    {
        "phased_plan": {
            "metrics": {"environment": 6, "finance": 2, "employment": -2, "team": 3},
            "relations": {"mayor": 5, "environment_director": 4, "county_secretary": -2},
            "flags": ["phased_plan", "asset_check"],
        },
        "state_owned_merge": {
            "metrics": {"environment": 5, "employment": 3, "finance": -6, "liability": 8},
            "relations": {"executive_vice_mayor": 8, "chairman": -8, "discipline": -4},
            "flags": ["merge_plan", "implicit_support"],
        },
        "enterprise_self_rescue": {
            "metrics": {"finance": 4, "employment": 2, "environment": -2, "liability": 2},
            "relations": {"chairman": 7, "banker": 3, "environment_director": -3},
            "flags": ["enterprise_window", "asset_check"],
        },
        "personal_control": {
            "metrics": {"admin": 2, "team": -4, "environment": -2},
            "relations": {"secretary_general": 4, "mayor": -4, "executive_vice_mayor": -2},
            "flags": ["personal_control", "parallel_plans"],
        },
    },
    {
        "conditional_support": {
            "metrics": {"employment": 4, "social": 3, "finance": -2, "admin": 4},
            "relations": {"county_secretary": 7, "mayor": 2},
            "flags": ["true_jobs", "training_commitment"],
            "commitment": "北山县完整上报就业名单后，市里优先安排培训和替代项目支持。",
        },
        "credit_signal": {
            "metrics": {"finance": 2, "employment": 3, "liability": 3},
            "relations": {"banker": 6, "chairman": 5, "discipline": -2},
            "flags": ["credit_signal", "enterprise_confidence"],
            "commitment": "市里公开支持保留合规产能，但不为企业融资提供担保。",
        },
        "hard_line": {
            "metrics": {"environment": 3, "team": -3, "admin": -2},
            "relations": {"county_secretary": -6, "chairman": -5, "environment_director": 3},
            "flags": ["hard_line"],
        },
        "balanced_bargain": {
            "metrics": {"environment": 3, "employment": 3, "admin": 3, "team": 2},
            "relations": {"county_secretary": 4, "banker": 3, "environment_director": 4, "chairman": 2},
            "flags": ["true_jobs", "asset_check", "staged_bargain"],
            "commitment": "名单、资产和环保节点核验后，市里落实培训并协助市场化授信评估。",
        },
    },
    {
        "record_dissent": {
            "metrics": {"org_credit": 5, "team": 4, "admin": 4, "liability": -4},
            "relations": {"mayor": 4, "discipline": 6, "executive_vice_mayor": -1},
            "flags": ["formal_report", "dissent_recorded"],
        },
        "unify_and_press": {
            "metrics": {"environment": 4, "admin": 2, "team": -2, "liability": 4},
            "relations": {"executive_vice_mayor": 3, "discipline": -3},
            "flags": ["unified_line", "hidden_dissent"],
        },
        "defer_decision": {
            "metrics": {"finance": 2, "environment": -5, "org_credit": -3, "liability": -1},
            "relations": {"discipline": 2, "environment_director": -3},
            "flags": ["decision_deferred"],
        },
        "executive_order": {
            "metrics": {"environment": 4, "admin": 2, "team": -5, "liability": 5},
            "relations": {"mayor": -5, "secretary_general": 2},
            "flags": ["personal_control", "direct_order"],
        },
    },
    {
        "acknowledge_adjust": {
            "metrics": {"org_credit": 4, "admin": 5, "environment": 2, "social": 2, "liability": -3},
            "relations": {"mayor": 3, "discipline": 5, "county_secretary": 2},
            "flags": ["corrected_openly"],
        },
        "double_down": {
            "metrics": {"environment": 3, "team": -3, "social": -4, "liability": 7},
            "relations": {"discipline": -6, "county_secretary": -3},
            "flags": ["suppressed_bad_news"],
        },
        "replace_lead": {
            "metrics": {"admin": 2, "team": -5, "org_credit": 1, "liability": -1},
            "relations": {"mayor": -2, "executive_vice_mayor": -5, "discipline": 3},
            "flags": ["lead_replaced", "accountability_review"],
        },
        "seek_province": {
            "metrics": {"org_credit": 3, "finance": 3, "environment": 3, "liability": -2},
            "relations": {"mayor": 3, "banker": 4, "county_secretary": 1},
            "flags": ["province_support", "formal_report"],
        },
    },
    {
        "transparent_review": {
            "metrics": {"org_credit": 7, "admin": 4, "social": 3, "liability": -7},
            "relations": {"discipline": 5, "mayor": 3, "environment_director": 3},
            "flags": ["transparent_final"],
        },
        "polish_report": {
            "metrics": {"org_credit": 2, "social": -2, "liability": 7},
            "relations": {"secretary_general": -2, "discipline": -5},
            "flags": ["polished_final"],
        },
        "blame_county": {
            "metrics": {"org_credit": 1, "team": -5, "admin": -3, "liability": 1},
            "relations": {"county_secretary": -10, "mayor": -2},
            "flags": ["blamed_county"],
        },
        "accept_responsibility": {
            "metrics": {"team": 7, "social": 3, "org_credit": 3, "liability": 2},
            "relations": {"mayor": 5, "county_secretary": 4, "discipline": 2},
            "flags": ["accepted_responsibility"],
        },
    },
]


TEMPLATE_REACTIONS: Dict[str, List[Dict[str, str]]] = {
    "mayor_compliance": [{"actor_id": "mayor", "text": "我来牵头，但请市委明确：没有落实的资金不能写进方案。"}],
    "delay_for_jobs": [{"actor_id": "environment_director", "text": "争取政策可以，但复核材料不能用延期申请代替真实整改。"}],
    "personal_taskforce": [{"actor_id": "mayor", "text": "市委直接抓可以更快，但政府系统需要一个明确的执行负责人。"}],
    "phased_plan": [{"actor_id": "county_secretary", "text": "县里配合分期，但首批停产名单必须和就业安排一起谈。"}],
    "state_owned_merge": [{"actor_id": "discipline", "text": "重组不是不能做，先把政府责任和未来补贴写清楚。"}],
    "enterprise_self_rescue": [{"actor_id": "chairman", "text": "只要不给企业判死刑，我们有把握自己找到资金。"}],
    "personal_control": [{"actor_id": "secretary_general", "text": "材料会更多，但再不确定牵头人，各单位就会继续等您的具体意见。"}],
    "conditional_support": [{"actor_id": "county_secretary", "text": "有了这个条件，县里可以把真实名单报上来，但项目支持要尽快落地。"}],
    "credit_signal": [{"actor_id": "banker", "text": "政策预期稳定后，分行愿意重新提交授信评估，但这不是放款承诺。"}],
    "hard_line": [{"actor_id": "county_secretary", "text": "县里执行没有问题，只是由此产生的稳定压力也请市里充分考虑。"}],
    "balanced_bargain": [{"actor_id": "mayor", "text": "可以按节点推进，但必须明确谁先做第一步，不能互相等条件。"}],
    "record_dissent": [{"actor_id": "discipline", "text": "把风险记清楚不是推责，是让后续调整还有制度空间。"}],
    "unify_and_press": [{"actor_id": "executive_vice_mayor", "text": "口径统一后我来压进度，但融资问题仍然需要尽快解决。"}],
    "defer_decision": [{"actor_id": "environment_director", "text": "材料可以再补，省里的时间不会因此停止。"}],
    "executive_order": [{"actor_id": "mayor", "text": "既然书记已经定调，政府会执行；需要提醒的是，具体责任仍要落到正式方案。"}],
    "acknowledge_adjust": [{"actor_id": "mayor", "text": "承认变化会难看一阵，但至少大家可以按真实条件重新安排。"}],
    "double_down": [{"actor_id": "discipline", "text": "如果真实情况已经变化，继续维持原口径会形成新的责任。"}],
    "replace_lead": [{"actor_id": "secretary_general", "text": "换人能够表明态度，但也要防止所有人先忙着证明问题与自己无关。"}],
    "seek_province": [{"actor_id": "banker", "text": "省级协调能让授信重新评估，但企业资产问题仍然绕不过去。"}],
    "transparent_review": [{"actor_id": "discipline", "text": "有些指标不好看，但真实材料和纠偏记录能够经得住后续检查。"}],
    "polish_report": [{"actor_id": "secretary_general", "text": "文字可以更凝练，但复核组会直接看现场和原始数据。"}],
    "blame_county": [{"actor_id": "county_secretary", "text": "市里如果把所有偏差都归到县里，后续工作很难再形成合力。"}],
    "accept_responsibility": [{"actor_id": "mayor", "text": "书记愿意承担统筹责任，政府这边也会把未完成事项接着做实。"}],
}


TEMPLATE_NARRATIVES: Dict[str, str] = {
    "mayor_compliance": "市政府获得了明确授权。财政部门的态度稍有稳定，工业系统则开始担心就业目标会被环保节点压住。",
    "delay_for_jobs": "企业和北山县暂时松了一口气，环保局却把省级复核倒计时写进了新的要情专报。",
    "personal_taskforce": "更多材料开始直接送到你的办公室。信息增加了，几个分管领导也更倾向于等待你的逐项判断。",
    "phased_plan": "方案第一次形成了可执行的时间线，但真实就业数字会让安置成本高于最初估计。",
    "state_owned_merge": "市属国企开始接触企业资产，推进速度明显加快；财政和纪委同时要求解释未来补贴边界。",
    "enterprise_self_rescue": "企业获得了短暂窗口，董事长公开表示有信心融资，银行仍未给出同样乐观的判断。",
    "personal_control": "三套方案继续竞争，所有人都在增加材料来影响你的判断，正式责任人依然模糊。",
    "conditional_support": "县里提交了更完整的就业底册，稳定风险随之上升。真实信息改善了决策，也制造了新的财政压力。",
    "credit_signal": "银行同意继续评估，企业将公开表态理解为政府保留产业的承诺，双方对信号的理解并不完全相同。",
    "hard_line": "没有人公开反对，但县、企和银行都只承诺完成自己最低限度的责任。",
    "balanced_bargain": "多方形成了节点清单。联盟比以前稳固，也更容易因为第一项延误而整体停滞。",
    "record_dissent": "常委会形成正式决定，保留意见被如实记入。执行者知道自己的责任，也知道哪些风险尚未解决。",
    "unify_and_press": "统一口径带来了短期动员效果，原有分歧没有消失，只是不再出现在正式材料中。",
    "defer_decision": "材料被退回，程序风险下降了一些，复核时间却进一步收紧。",
    "executive_order": "各单位迅速进入执行，但新的汇报几乎都直接指向你的办公室。",
    "acknowledge_adjust": "修正后的材料不再好看，却重新建立了可以工作的事实基础。",
    "double_down": "节点暂时没有改变，基层开始把坏消息留在内部，等待更安全的汇报时机。",
    "replace_lead": "人事调整恢复了表面控制，也让其他干部在提供坏消息前更加谨慎。",
    "seek_province": "省里没有承诺兜底，但同意协调一次专题沟通，本地方案获得了重新安排节点的机会。",
    "transparent_review": "复核材料中的问题没有被掩盖，整改被评价为仍在进行，但责任和后续节点基本清楚。",
    "polish_report": "工作总结显得完整顺畅，现场核验却让几处原则性表述面临进一步追问。",
    "blame_county": "市级决策记录得到保护，北山县的配合意愿和班子共同担责明显下降。",
    "accept_responsibility": "你把统筹责任留在自己名下，保护了执行链，但也让后续整改结果与你个人评价绑定得更紧。",
}


RESPONSIBILITIES: Dict[str, Dict[str, Any]] = {
    "mayor_compliance": {"lead_actor_id": "mayor", "lead_label": "市长周立衡牵头", "participants": ["市政府办", "生态环境局", "工信局", "北山县"], "procedure": "市政府专题会形成三案后报市委", "record": "书面领导指令与专题会纪要"},
    "delay_for_jobs": {"lead_actor_id": "industry_vice_mayor", "lead_label": "副市长邵文远牵头", "participants": ["工信局", "北山县", "三家企业"], "procedure": "先行沟通省级部门并提交展期依据", "record": "专项请示与企业整改责任书"},
    "personal_taskforce": {"lead_actor_id": "secretary_general", "lead_label": "市委秘书长组织专班", "participants": ["市委督查室", "市政府相关部门"], "procedure": "市委专项督办，重大方案另行上会", "record": "专班任务清单与书记批示"},
    "phased_plan": {"lead_actor_id": "mayor", "lead_label": "市长周立衡牵头", "participants": ["生态环境局", "财政局", "人社局", "北山县"], "procedure": "方案论证后提交常委会审议", "record": "分期方案送审稿"},
    "state_owned_merge": {"lead_actor_id": "executive_vice_mayor", "lead_label": "常务副市长罗志诚牵头", "participants": ["市国资委", "市属国企", "财政局"], "procedure": "开展资产、现金流和合规论证后上会", "record": "重组可研与风险审查意见"},
    "enterprise_self_rescue": {"lead_actor_id": "industry_vice_mayor", "lead_label": "副市长邵文远牵头", "participants": ["工信局", "企业", "银行", "生态环境局"], "procedure": "签订限期整改和资产披露条件", "record": "企业责任书与核查台账"},
    "personal_control": {"lead_actor_id": "secretary_general", "lead_label": "市委秘书长汇总、书记直听", "participants": ["三套方案起草组"], "procedure": "并行论证，暂不产生最终方案效力", "record": "书记专题调度记录"},
    "conditional_support": {"lead_actor_id": "county_secretary", "lead_label": "北山县委书记先报真实名单", "participants": ["北山县", "市人社局", "市发改委"], "procedure": "名单核验后再安排培训与项目程序", "record": "条件承诺与就业核验清单"},
    "credit_signal": {"lead_actor_id": "banker", "lead_label": "银行分行重新评估授信", "participants": ["企业", "市金融办", "工信局"], "procedure": "企业资产穿透后报省行审批", "record": "政策说明与授信评估意见"},
    "hard_line": {"lead_actor_id": "mayor", "lead_label": "市政府按既定分工推进", "participants": ["北山县", "企业", "相关部门"], "procedure": "不新增交换条件，按责任书督办", "record": "督办通知"},
    "balanced_bargain": {"lead_actor_id": "mayor", "lead_label": "市长周立衡统筹条件清单", "participants": ["北山县", "企业", "银行", "生态环境局"], "procedure": "分节点确认履约后进入各自正式程序", "record": "多方协调纪要与条件清单"},
    "record_dissent": {"lead_actor_id": "mayor", "lead_label": "市政府组织实施", "participants": ["市委常委会", "市政府相关部门", "北山县"], "procedure": "常委会充分讨论、如实记载后通过", "record": "常委会纪要、决定与省级报告"},
    "unify_and_press": {"lead_actor_id": "executive_vice_mayor", "lead_label": "常务副市长压实节点", "participants": ["市政府相关部门", "北山县"], "procedure": "常委会形成统一意见后执行", "record": "统一口径的常委会纪要"},
    "defer_decision": {"lead_actor_id": "mayor", "lead_label": "市政府补充论证", "participants": ["财政局", "人社局", "生态环境局"], "procedure": "补齐数据和资金来源后再次上会", "record": "退回补充论证清单"},
    "executive_order": {"lead_actor_id": "secretary_general", "lead_label": "市委办按书记定调督办", "participants": ["市政府相关单位"], "procedure": "先行执行，需补齐正式责任和实施文件", "record": "书记讲话记录与督办件"},
    "acknowledge_adjust": {"lead_actor_id": "mayor", "lead_label": "原牵头人继续纠偏", "participants": ["原执行单位", "市委办"], "procedure": "专题调度修正后补充报告", "record": "纠偏纪要与修订方案"},
    "double_down": {"lead_actor_id": "mayor", "lead_label": "原责任链维持不变", "participants": ["原执行单位"], "procedure": "内部调度、不修改正式节点", "record": "内部督办通知"},
    "replace_lead": {"lead_actor_id": "secretary_general", "lead_label": "市委组织调整责任链", "participants": ["新旧牵头人", "纪委监委"], "procedure": "调整分工并核查前期信息责任", "record": "分工调整与核查决定"},
    "seek_province": {"lead_actor_id": "mayor", "lead_label": "市长组织专题上报", "participants": ["市政府办", "省级相关部门"], "procedure": "正式报告变化并请求协调", "record": "专题报告与省级沟通纪要"},
    "transparent_review": {"lead_actor_id": "mayor", "lead_label": "市长作工作汇报", "participants": ["生态环境局", "北山县", "市委办"], "procedure": "材料、现场和未完成事项一并接受核验", "record": "复核汇报与后续整改清单"},
    "polish_report": {"lead_actor_id": "secretary_general", "lead_label": "市委办形成成绩口径", "participants": ["相关材料单位"], "procedure": "以总结稿为主接受复核", "record": "十二周工作总结"},
    "blame_county": {"lead_actor_id": "county_secretary", "lead_label": "北山县说明执行偏差", "participants": ["北山县", "相关企业"], "procedure": "市县分列决策和执行责任", "record": "责任说明与问题清单"},
    "accept_responsibility": {"lead_actor_id": None, "lead_label": "市委书记承担统筹责任", "participants": ["市级班子", "原执行单位"], "procedure": "完整说明问题并请求继续整改", "record": "书记表态与后续责任书"},
}


TEMPLATE_INQUIRY: Dict[str, Dict[str, Any]] = {
    "mayor": {"reply": "我最担心的不是方案写不出来，而是把没有来源的钱写成政府承诺。金融办判断，北岭能源如果续贷中断，两个月内可能连工资都吃紧。这个情况目前只在内部监测里。", "used_belief_ids": ["mayor_cash_crisis", "mayor_budget_gap"], "consequence_note": "你获得了企业现金流和市级财政边界的内部判断。"},
    "secretary_general": {"reply": "县里的就业数字改过三次，最后一次把花名册附件撤了。还有一件事：前任那次专题会口头谈过市属国企参与，正式纪要却只写了‘统筹研究’。两件事都值得单独核。", "used_belief_ids": ["secretary_jobs_revision", "secretary_old_minutes"], "consequence_note": "你发现材料流转和历史纪要存在两处异常。"},
    "executive_vice_mayor": {"reply": "国企整合能把设备、订单和环保投入放进一个项目，速度最快。前两年确实有资金缺口，我认为属于项目培育期，但财政和国资部门会要求把四点六亿元怎么闭合说清。", "used_belief_ids": ["vice_merge_gap"], "consequence_note": "常务副市长承认重组底稿存在较大前期资金缺口。"},
    "industry_vice_mayor": {"reply": "企业不是完全没投入，但去年承诺的八亿元最终到账不到两亿元。再给窗口可以，必须把续贷和到账节点盯死，否则又会变成一次口头承诺。", "used_belief_ids": ["industry_failed_promise"], "consequence_note": "你得知企业过去的自筹承诺履约很差。"},
    "discipline": {"reply": "现在不能给谁下结论。纪委确实收到一封反映县企利益往来的匿名信，还没有核实。我建议把资金、名单和前期会议分开核，不要用一个传闻替代证据。", "used_belief_ids": ["discipline_letter"], "consequence_note": "你得知存在未核实的县企关系线索，但它还不能作为定性依据。"},
    "county_secretary": {"reply": "七千四百是按长期合同和主厂区统计的口径，县里还在复核劳务和配套人员。书记如果要我把最宽口径全报上来，我需要先知道市里能承担什么安置支持。", "used_belief_ids": ["county_real_jobs"], "consequence_note": "高维民承认就业统计口径偏窄，但没有直接报出内部总数。"},
    "environment_director": {"reply": "二号线正在检修，高污染工段已经停着。十天内把停产范围和在线监测固化下来，成本最低；错过这个窗口再要求退出，企业一定会说是政府额外造成损失。", "used_belief_ids": ["environment_window"], "consequence_note": "你获得了一个十日内可利用的现场整改窗口。"},
    "chairman": {"reply": "集团账面资产三十多亿元，不是外面说的资不抵债。真正的问题是政策预期：如果政府要强制并购，我们不可能继续把订单和团队留在这里等。具体抵押情况需要财务再整理。", "used_belief_ids": ["chairman_collateral_truth", "chairman_order_move"], "consequence_note": "韩泽强调账面资产并暗示产业外移，却回避了可自由抵押资产。"},
    "banker": {"reply": "分行愿意评估，但省行要求先把资产穿透做完。市里给稳定政策信号有帮助，不能替代现金流和担保，更不能理解成我已经答应放款。", "used_belief_ids": ["bank_credit_line"], "consequence_note": "银行明确了分行权限和新增授信的硬条件。"},
}


def initial_state() -> Dict[str, Any]:
    return deepcopy(INITIAL_STATE)


def responsibility_for_tag(strategy_tag: str) -> Dict[str, Any]:
    return deepcopy(RESPONSIBILITIES[strategy_tag])


def actor_agent_context(actor_id: str) -> Dict[str, Any]:
    if actor_id not in ACTORS or actor_id not in ACTOR_AGENT_CONTEXT:
        raise KeyError(actor_id)
    return {
        "id": actor_id,
        **deepcopy(ACTORS[actor_id]),
        **deepcopy(ACTOR_AGENT_CONTEXT[actor_id]),
    }


def actor_belief_ids(actor_id: str) -> List[str]:
    return [item["id"] for item in ACTOR_AGENT_CONTEXT[actor_id]["beliefs"]]


def turn_definition(turn_index: int, state: Dict[str, Any]) -> Dict[str, Any]:
    turn = deepcopy(TURNS[turn_index])
    if turn_index == 1:
        if "audit_history" in state["flags"]:
            turn["reports"].append(
                {
                    "id": "history_note",
                    "source": "市委秘书长唐敏",
                    "title": "前期会议记录核查",
                    "summary": "前任曾口头同意必要时由市属国企参与保障。",
                    "detail": "正式纪要只写了“统筹研究”，没有资金承诺。多名参会者对此有不同理解。",
                    "tone": "warning",
                }
            )
    if turn_index == 4:
        turn["reports"] = [shock_report(state)]
    return turn


def shock_report(state: Dict[str, Any]) -> Dict[str, str]:
    shock = state.get("shock")
    reports = {
        "credit_freeze": {
            "id": "credit_freeze",
            "source": "市政府金融办",
            "title": "银行暂停新增授信",
            "summary": "银行发现企业可抵押资产少于此前披露，暂停新增技改贷款。",
            "detail": "现有贷款没有立即抽回，但企业两周内可能出现工资和工程款支付困难。",
            "tone": "danger",
        },
        "jobs_leak": {
            "id": "jobs_leak",
            "source": "市委值班室",
            "title": "就业名单低报问题被举报",
            "summary": "网络流传的企业用工表显示，受影响人数明显高于北山县此前上报。",
            "detail": "县里解释为统计口径不同。省级复核联络员已经询问数据是否需要修正。",
            "tone": "danger",
        },
        "orders_move": {
            "id": "orders_move",
            "source": "工信局紧急报告",
            "title": "企业开始向外转移订单",
            "summary": "北岭能源集团将部分长期订单转给邻市关联企业。",
            "detail": "董事长称这是正常商业安排，工信局担心下一步转移技术和骨干团队。",
            "tone": "danger",
        },
        "signature_refusal": {
            "id": "signature_refusal",
            "source": "市生态环境局",
            "title": "环保局拒绝在进度报告上签字",
            "summary": "现场监测无法支持企业自报的整改完成率。",
            "detail": "环保局要求修正报告并重新核验，否则只愿附保留意见上报。",
            "tone": "danger",
        },
    }
    return deepcopy(reports.get(shock, reports["credit_freeze"]))


def allowed_tags(turn_index: int) -> List[str]:
    return [option["id"] for option in TURNS[turn_index]["options"]]


def option_by_id(turn_index: int, option_id: str) -> Dict[str, str]:
    for option in TURNS[turn_index]["options"]:
        if option["id"] == option_id:
            return option
    raise KeyError(option_id)
