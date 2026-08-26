from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


METRIC_DEFINITIONS = [
    ("finance", "财政韧性", "市县两级承受新增支出和融资冲击的能力", True),
    ("employment", "就业稳定", "产业调整对就业与收入的综合影响", True),
    ("environment", "环境合规", "整改进度、数据真实性与上级核验把握", True),
    ("flood", "防汛准备", "风险排查、物资、预案和基层执行状态", True),
    ("social", "社会信任", "群众预期、矛盾化解与公开沟通状况", True),
    ("org_credit", "组织信用", "上级与班子对玩家判断和执行力的评价", True),
    ("team", "班子协调", "市级领导班子分工、信任与共同担责程度", True),
    ("admin", "行政能力", "部门协同、真实报告与持续执行能力", True),
    ("liability", "责任暴露", "财政、程序、数据和承诺留下的追责风险", False),
]


ACTORS: Dict[str, Dict[str, Any]] = {
    "mayor": {
        "name": "周立衡",
        "title": "市委副书记、市长",
        "public_position": "支持整改，但反对没有资金来源的政治表态。",
        "known_note": "掌握财政与行政执行链，希望书记尊重政府分工。",
        "work_style": "数字敏感、措辞克制，习惯先问资金和责任边界。",
        "private_goal": "推进整改但不让政府形成新的兜底责任，同时维护市政府责任链。",
        "beliefs": [
            {"id": "mayor_cash_crisis", "content": "北岭能源若银行不续作，两个月内可能无法按时发薪。", "source": "市金融办内部监测"},
            {"id": "mayor_budget_gap", "content": "市级灵活预算不足以覆盖大规模技改补贴。", "source": "财政局近期测算"},
        ],
    },
    "secretary_general": {
        "name": "唐敏",
        "title": "市委常委、秘书长",
        "public_position": "建议先分清材料来源、程序和待拍板事项。",
        "known_note": "掌握议程、日程和材料流转，是你最直接的信息渠道。",
        "work_style": "善于从材料改动和会前动向判断真实分歧。",
        "private_goal": "帮助新书记建立可靠的信息渠道，同时维持市委运转秩序。",
        "beliefs": [
            {"id": "secretary_jobs_revision", "content": "北山县送审稿三次下调就业影响数，最后删去了花名册附件。", "source": "市委办材料流转记录"},
            {"id": "secretary_old_minutes", "content": "前任专题会曾口头提到市属国企参与保障，正式纪要措辞含混。", "source": "会务人员回忆与纪要草稿"},
        ],
    },
    "fulltime_deputy": {
        "name": "顾明川",
        "title": "市委副书记",
        "public_position": "主张先把跨部门责任和基层承受能力梳理清楚。",
        "known_note": "长期在岚州工作，熟悉县区干部和群团系统。",
        "work_style": "少抢话，重视班子共识和基层可执行性。",
        "private_goal": "维持班子稳定，并避免新书记过快被少数强势方案绑住。",
        "beliefs": [
            {"id": "deputy_county_mood", "content": "北山县干部普遍认为市里会把整改成本留给县里。", "source": "近期县区座谈"},
        ],
    },
    "executive_vice_mayor": {
        "name": "罗志诚",
        "title": "市委常委、常务副市长",
        "public_position": "主张市属国企参与整合，以时间换空间。",
        "known_note": "执行力强，希望主导能够形成成绩的重组项目。",
        "work_style": "行动快、项目化思维强，倾向先形成方案再补程序。",
        "private_goal": "争取主导重组项目，并让财政风险看起来可被项目现金流覆盖。",
        "beliefs": [
            {"id": "vice_merge_gap", "content": "国企整合方案前两年现金流缺口约四点六亿元。", "source": "重组测算底稿"},
        ],
    },
    "industry_vice_mayor": {
        "name": "邵文远",
        "title": "副市长",
        "public_position": "产业不能垮，主张争取更充足的整改窗口。",
        "known_note": "过去两年一直联系企业，对产业情况熟悉。",
        "work_style": "熟悉企业诉求，面对追责时较为防御。",
        "private_goal": "保住产业连续性，也避免过去支持展期的判断被追责。",
        "beliefs": [
            {"id": "industry_failed_promise", "content": "企业去年承诺自筹八亿元，实际到账不足两亿元。", "source": "工信局调度台账"},
        ],
    },
    "discipline": {
        "name": "贺兰",
        "title": "市委常委、市纪委书记",
        "public_position": "改革可以探索，资金与数据必须经得住检查。",
        "known_note": "已关注前期会议和县企关系，但尚未形成结论。",
        "work_style": "不轻易定性，习惯追问谁签字、谁知情、依据是什么。",
        "private_goal": "保留改革空间，但阻止数据造假、口头兜底和责任故意模糊。",
        "beliefs": [
            {"id": "discipline_letter", "content": "纪委收到县企利益往来的匿名反映，目前尚未核实。", "source": "匿名信访件"},
        ],
    },
    "organization_minister": {
        "name": "孟昭宁",
        "title": "市委常委、组织部部长",
        "public_position": "干部使用应与任务难度、履职记录和班子分工一致。",
        "known_note": "关注谁真正承担工作、谁只在材料上表态。",
        "work_style": "观察细、表态谨慎，不轻易讨论具体人事结论。",
        "private_goal": "积累真实履职记录，避免被临时情绪推动干部调整。",
        "beliefs": [
            {"id": "organization_overload", "content": "市政府几个关键部门近期任务明显过载。", "source": "干部日常了解"},
        ],
    },
    "propaganda_minister": {
        "name": "苏闻",
        "title": "市委常委、宣传部部长",
        "public_position": "公开信息必须可核验，不能让统一口径替代事实核查。",
        "known_note": "掌握媒体协调和舆情渠道。",
        "work_style": "重视传播节奏，会提醒哪些表述可能被外界误读。",
        "private_goal": "避免舆情失控，也避免宣传系统替业务部门掩盖事实。",
        "beliefs": [
            {"id": "propaganda_video_spread", "content": "园区夜间排放视频正在本地多个群组二次传播。", "source": "网络舆情监测"},
        ],
    },
    "political_legal_secretary": {
        "name": "程岳",
        "title": "市委常委、政法委书记",
        "public_position": "稳定风险要基于真实人数和具体矛盾，不能只看是否出现聚集。",
        "known_note": "熟悉信访、公安和基层治理渠道。",
        "work_style": "强调预案和底线，同时警惕把一般诉求过度安全化。",
        "private_goal": "尽早识别可化解矛盾，避免局势升级后只剩强制处置。",
        "beliefs": [
            {"id": "political_legal_wage_risk", "content": "园区两家承包商已出现工资延迟迹象。", "source": "基层矛盾排查"},
        ],
    },
    "united_front_minister": {
        "name": "柳清和",
        "title": "市委常委、统战部部长",
        "public_position": "应让企业、商会和职工代表在方案形成前表达真实顾虑。",
        "known_note": "与民营企业和行业协会联系较多。",
        "work_style": "擅长缓和措辞，也会为非公企业争取表达空间。",
        "private_goal": "避免企业把整改理解成所有权重组的借口。",
        "beliefs": [
            {"id": "united_front_owner_fear", "content": "几名企业负责人担心整改最终演变为低价整合。", "source": "商会私下反映"},
        ],
    },
    "garrison_commissar": {
        "name": "徐峥",
        "title": "市委常委、岚州军分区政委",
        "public_position": "对专业经济方案不轻易表态，关注应急能力和集体程序。",
        "known_note": "日常不介入具体产业管理。",
        "work_style": "发言简短，程序性事项上态度明确。",
        "private_goal": "确保需要集体决定的事项经过充分讨论。",
        "beliefs": [
            {"id": "garrison_emergency_capacity", "content": "汛期跨部门应急联络最近一次演练存在响应延迟。", "source": "应急联动演练记录"},
        ],
    },
    "county_secretary": {
        "name": "高维民",
        "title": "北山县委书记",
        "public_position": "服从市委决定，但就业安置必须得到市级支持。",
        "known_note": "控制基层执行和稳定工作，县财政高度依赖焦化。",
        "work_style": "口头服从、实际谈条件，最在意县里先担责却拿不到资源。",
        "private_goal": "避免县财政、就业和个人评价同时失守。",
        "beliefs": [
            {"id": "county_real_jobs", "content": "内部最宽口径约一万一千二百人，正式上报七千四百人。", "source": "县人社局未上报花名册"},
            {"id": "county_subsidy_arrears", "content": "北山县尚欠企业以前年度奖补约六千八百万元。", "source": "县财政支付台账"},
        ],
    },
    "environment_director": {
        "name": "许仲平",
        "title": "市生态环境局局长",
        "public_position": "必须完成真实、可核验的阶段目标。",
        "known_note": "不愿在无法确认的数据和整改报告上签字。",
        "work_style": "专业直接，宁可得罪人也不替失真数据背书。",
        "private_goal": "完成可核验整改并保护专业签字责任。",
        "beliefs": [
            {"id": "environment_window", "content": "北岭二号线正在检修，十日内固化停产和监测安排成本最低。", "source": "现场检查记录"},
        ],
    },
    "chairman": {
        "name": "韩泽",
        "title": "北岭能源集团董事长",
        "public_position": "企业愿意整改，但需要银行和政府共同支持。",
        "known_note": "最大企业负责人，反对失去控制权。",
        "work_style": "强调产业贡献，对资产和现金流选择性披露。",
        "private_goal": "保住企业控制权并争取续贷。",
        "beliefs": [
            {"id": "chairman_collateral_truth", "content": "可自由新增抵押的资产不足六亿元。", "source": "集团融资台账"},
            {"id": "chairman_order_move", "content": "若政府明确强制并购，集团准备转移订单和技术团队。", "source": "董事长内部预案"},
        ],
    },
    "banker": {
        "name": "魏舒",
        "title": "省城商行岚州分行行长",
        "public_position": "只支持有现金流和足额担保的项目。",
        "known_note": "可以建议授信，最终仍需省行审批。",
        "work_style": "只谈可核验条件，不接受含混政治承诺。",
        "private_goal": "控制现有贷款恶化，避免分行承担无法审批的风险。",
        "beliefs": [
            {"id": "bank_credit_line", "content": "新增授信必须先完成资产穿透，政府口头支持不能替代担保。", "source": "省行风险提示"},
        ],
    },
    "superior": {
        "name": "沈开济",
        "title": "省委副书记",
        "public_position": "地方要如实报告，也要形成能够落地的处置方案。",
        "known_note": "通常先通过省委办公厅和书面材料掌握情况。",
        "work_style": "追问问题是否真实、责任是否清楚、地方是否只在上交矛盾。",
        "private_goal": "判断岚州班子能否在不掩盖风险的情况下形成执行力。",
        "beliefs": [
            {"id": "superior_prior_delay", "content": "岚州此前两次申请分阶段推进，省里对再次只报困难较为敏感。", "source": "省委办公厅历史材料"},
        ],
    },
}


STANDING_COMMITTEE_MEMBER_IDS = [
    "player",
    "mayor",
    "fulltime_deputy",
    "secretary_general",
    "executive_vice_mayor",
    "discipline",
    "organization_minister",
    "propaganda_minister",
    "political_legal_secretary",
    "united_front_minister",
    "garrison_commissar",
]


MEETING_TYPES = {
    "symposium": {
        "label": "座谈会",
        "cost": 2,
        "formal_effect": "听取意见和形成问题清单，不能直接形成重大决定。",
    },
    "secretary_special": {
        "label": "书记专题会",
        "cost": 2,
        "formal_effect": "可以酝酿方案和安排准备任务，不能替代常委会。",
    },
    "coordination": {
        "label": "工作协调会",
        "cost": 2,
        "formal_effect": "可以协调已有任务和权限内执行事项。",
    },
    "standing_committee": {
        "label": "市委常委会",
        "cost": 2,
        "formal_effect": "满足成员、讨论和表决条件后可形成党委决定；行政事项仍需后续程序。",
    },
}


LOCATIONS = {
    "beishan_park": {
        "label": "北山焦化产业园",
        "notified": "园区准备了完整台账和固定参观点，企业负责人均在场；部分生产区在到访前完成了临时清理。",
        "unannounced": "你从侧门进入一处检修区，没有见到主要负责人，但看见劳务人员名单与县里材料口径不一致。",
        "reveals": ["environment_window", "county_real_jobs"],
    },
    "employment_center": {
        "label": "北山县就业服务中心",
        "notified": "大厅安排了已登记职工代表，培训项目展示完整，但劳务和上下游人员没有进入样本。",
        "unannounced": "窗口工作人员临时调出两套不同口径的登记表，解释称一套用于稳岗、一套用于失业监测。",
        "reveals": ["county_real_jobs"],
    },
    "flood_site": {
        "label": "南川河防汛风险点",
        "notified": "属地准备了巡堤记录、物资清单和修复计划，现场通道已经清理。",
        "unannounced": "值守人员能说明险段位置，但一批沙袋已老化，最近一次巡查照片与文字结论并不完全相符。",
        "reveals": ["flood_photo_mismatch"],
    },
}


INITIAL_METRICS = {
    "finance": 42,
    "employment": 68,
    "environment": 31,
    "flood": 48,
    "social": 60,
    "org_credit": 50,
    "team": 48,
    "admin": 56,
    "liability": 35,
}


INITIAL_ISSUES = [
    {
        "id": "industry_rectification",
        "title": "北山产业整改",
        "summary": "就业、资产和整改进度存在多套口径，上级要求近期报送阶段情况。",
        "pressure": "high",
        "known_status": "材料互相矛盾，尚未形成正式方案。",
    },
    {
        "id": "fiscal_priorities",
        "title": "财政与项目排序",
        "summary": "财政空间偏紧，多项支持诉求可能互相挤压。",
        "pressure": "medium",
        "known_status": "市政府正在准备滚动支出安排。",
    },
    {
        "id": "flood_preparation",
        "title": "汛期准备",
        "summary": "两个县区的风险附件口径不一致，极端天气是否出现尚不确定。",
        "pressure": "medium",
        "known_status": "已收到汇总报告，尚未独立核实。",
    },
]


INITIAL_DOCUMENTS = [
    {
        "id": "doc-environment",
        "title": "北山焦化阶段整改情况报告",
        "document_type": "report",
        "author_id": "environment_director",
        "status": "received",
        "confidentiality": "内部",
        "summary": "建议尽快明确第一批核验对象和监测节点。",
        "content": "现有两条生产线尚不满足阶段核验要求。生态环境局建议先固定停产范围、在线监测节点和签字责任。报告没有测算就业与财政影响。",
        "recipient_ids": ["player"],
        "source_document_ids": [],
        "formal_effect": "情况报告，不产生关停决定。",
    },
    {
        "id": "doc-county-request",
        "title": "关于支持重点产业稳岗的请示",
        "document_type": "request",
        "author_id": "county_secretary",
        "status": "received",
        "confidentiality": "内部",
        "summary": "北山县报称直接受影响就业七千四百人，请求市级预留安置支持。",
        "content": "县里建议优先保持连续生产，并在市级项目和培训资金中给予支持。附件没有用工花名册，且就业数字低于工信部门初测。",
        "recipient_ids": ["player"],
        "source_document_ids": [],
        "formal_effect": "请示，等待批示或转办。",
    },
    {
        "id": "doc-fiscal-note",
        "title": "市级财政承受能力提示",
        "document_type": "briefing",
        "author_id": "mayor",
        "status": "received",
        "confidentiality": "内部",
        "summary": "现有预算无法覆盖大规模补贴或兜底融资。",
        "content": "市政府建议先由企业和银行提出市场化方案。任何国企过桥、回购或新增补贴均需重新测算并履行相应程序。",
        "recipient_ids": ["player"],
        "source_document_ids": [],
        "formal_effect": "风险提示，不是资金决定。",
    },
    {
        "id": "doc-flood",
        "title": "汛前风险排查汇总",
        "document_type": "report",
        "author_id": "secretary_general",
        "status": "received",
        "confidentiality": "内部",
        "summary": "两个县区对南川河险段的风险等级和物资数量填报不一致。",
        "content": "水利局汇总认为总体可控，但南川区附件将一处险段列为已完成修复，属地照片仍显示临时围挡。建议补充复核。",
        "recipient_ids": ["player"],
        "source_document_ids": [],
        "formal_effect": "风险报告，可据此交办核查。",
    },
    {
        "id": "doc-superior-notice",
        "title": "关于报送北山产业整改简要情况的通知",
        "document_type": "notice",
        "author_id": "superior",
        "status": "received",
        "confidentiality": "内部",
        "summary": "省委办公厅要求五个游戏日内报送简要情况，是否面谈另行通知。",
        "content": "报告应说明基本事实、主要风险、已经采取的措施、尚需协调事项和下一步安排。不得只报困难，不得隐去重要数据差异。",
        "recipient_ids": ["player"],
        "source_document_ids": [],
        "formal_effect": "上级报送要求。",
    },
]


TEMPLATE_UTTERANCES = {
    "mayor": "我建议先把资金来源和政府责任讲清。没有落实的钱不能写成承诺，行政方案也需要明确牵头人。",
    "secretary_general": "目前材料之间还有明显矛盾。会议可以先决定核什么、由谁起草，不宜把未核实数字写成统一结论。",
    "fulltime_deputy": "县里最担心的是先担责任、后等资源。方向可以定，但基层承受边界和反馈节点应当一起写清。",
    "executive_vice_mayor": "如果只做零散整改，产业链很难稳住。国企整合可以形成项目，但需要允许我们把资产和现金流先做穿透。",
    "industry_vice_mayor": "企业过去自筹没有完全兑现，但集中停产的就业代价同样真实。建议保留分期和企业自救窗口。",
    "discipline": "可以探索，但数据、资金和不同意见必须如实记录。程序完整不能替代实体合规。",
    "organization_minister": "请把任务落到具体岗位和期限。频繁换人不能代替对职责、资源和工作量的判断。",
    "propaganda_minister": "现在外界已经在传播排放视频。公开表述应与可核验事实一致，也要说明哪些仍在调查。",
    "political_legal_secretary": "就业口径不清会直接影响稳定预案。不能只看有没有聚集，还要看工资、劳务和家庭收入。",
    "united_front_minister": "企业担心整改被理解为强制整合。最好让企业说明资产和自救条件，再判断其可信度。",
    "garrison_commissar": "专业方案由主管同志说明。我只提醒一点：需要集体决定的事项应充分讨论，不能用临时口头意见代替。",
    "county_secretary": "县里执行市委决定，但就业和财政压力必须一并考虑。不能要求县里先把全部风险摊开，却不给任何支持路径。",
    "environment_director": "二号线检修是一个真实窗口。只要尽快固定停产范围和监测节点，可以降低后续整改成本。",
    "chairman": "企业愿意整改，但如果政策信号是强制并购，订单和技术团队都不可能原地等待。",
    "banker": "分行可以继续评估，前提是资产穿透和现金流真实。政策信号不能替代省行审批。",
    "superior": "我关心的不是材料写得多完整，而是岚州是否掌握真实情况、形成责任清楚且能执行的安排。",
}


def actor_context(actor_id: str) -> Dict[str, Any]:
    if actor_id not in ACTORS:
        raise KeyError(actor_id)
    return {"id": actor_id, **deepcopy(ACTORS[actor_id])}


def actor_belief_ids(actor_id: str) -> List[str]:
    return [item["id"] for item in ACTORS[actor_id]["beliefs"]]


def actor_label(actor_id: str) -> str:
    if actor_id == "player":
        return "市委书记"
    actor = ACTORS.get(actor_id)
    return actor["name"] if actor else actor_id
