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


PUBLIC_REFERENCE_MATERIALS: List[Dict[str, Any]] = [
    {
        "id": "ref-city-geography",
        "category": "市情总览",
        "title": "岚州市自然地理与空间格局",
        "subtitle": "区位、地貌、水系与气候",
        "updated_date": "2025-12",
        "summary": "岚州位于虚构的澄江省中西部，山地丘陵与河谷盆地相间，汛期降雨集中。",
        "sections": [
            {
                "heading": "区位与面积",
                "body": "全市国土面积约一万二千六百四十平方公里，东接省会经济圈，西部进入丘陵山地，南北之间依靠河谷和两条铁路通道联系。",
            },
            {
                "heading": "地貌与土地",
                "body": "低山约占四成、丘陵约占三成五、河谷平坝约占四分之一。建设用地主要集中在南川、临江两个城区和北山产业走廊，西部生态保护空间较多。",
            },
            {
                "heading": "水系与气候",
                "body": "南川河自西北向东南穿城汇入澄江，北部支流坡陡流急。多年平均降水量约九百一十毫米，约六成五集中在五月至九月，短时强降雨容易造成山洪、城区内涝和中小河流险情。",
            },
        ],
        "source_note": "虚构资料，综合岚州市国土空间规划、水资源公报和气象常年值形成。",
    },
    {
        "id": "ref-city-society",
        "category": "市情总览",
        "title": "人口、就业与公共服务",
        "subtitle": "人口结构、劳动力与基本公共资源",
        "updated_date": "2025-12",
        "summary": "全市常住人口约三百七十八万，人口外流、县域老龄化和产业就业集中并存。",
        "sections": [
            {
                "heading": "人口结构",
                "body": "常住人口约三百七十八万，户籍人口约四百一十六万，常住人口城镇化率约百分之五十八点四。六十岁及以上人口约占百分之二十一，青壮年净流出主要发生在青源、和州等县。",
            },
            {
                "heading": "就业结构",
                "body": "城镇就业主要集中在制造业、建筑业、商贸物流和公共服务；县域仍有较多农业人口。能源化工及上下游就业具有地区集中性，单一企业或园区波动可能迅速传导到劳务、运输和家庭收入。",
            },
            {
                "heading": "教育医疗",
                "body": "全市有一所本科院校、两所高职院校和三家三级医院，优质高中与专科医疗主要集中在两个城区。山区乡镇的师资、急救半径和养老照护能力相对薄弱。",
            },
        ],
        "source_note": "虚构资料，采用统计公报和公共服务资源名录的公开口径。",
    },
    {
        "id": "ref-city-economy",
        "category": "市情总览",
        "title": "经济结构与财政基本盘",
        "subtitle": "产业、投资、财政与国有经济",
        "updated_date": "2025-12",
        "summary": "岚州经济总量约二千一百四十八亿元，工业比重较高，财政支出依赖转移支付且县区分化明显。",
        "sections": [
            {
                "heading": "经济总量",
                "body": "二〇二五年地区生产总值约二千一百四十八亿元，三次产业结构约为十三点八、四十二点六和四十三点六。支柱行业包括能源化工、装备制造、农产品加工和商贸物流。",
            },
            {
                "heading": "财政收支",
                "body": "全市一般公共预算收入约一百五十六亿元，一般公共预算支出约四百二十七亿元。县区基本民生和基层运转较依赖上级转移支付，土地相关收入下降后，新增项目和产业支持空间收窄。",
            },
            {
                "heading": "发展约束",
                "body": "传统产业设备更新、污染治理和安全改造需求集中；本地民营企业融资抵押物不足，市属国企承担基础设施和政策性任务较多。公开规划把先进装备、绿色化工和现代农业列为转型方向，但项目成熟度不一。",
            },
        ],
        "source_note": "虚构资料，金额为上一完整统计年度公开口径，不等同于当前可支配资金。",
    },
    {
        "id": "ref-city-infrastructure",
        "category": "市情总览",
        "title": "交通、能源与防灾基础",
        "subtitle": "城市运行所依赖的公共设施",
        "updated_date": "2025-12",
        "summary": "岚州对外通道基本成形，但县域路网、水利设施和老城区管网仍有明显短板。",
        "sections": [
            {
                "heading": "综合交通",
                "body": "两条干线铁路、三条高速公路和一座区域货运编组站构成主要对外通道。北山工业品运输对一条南北货运走廊依赖较高，山区普通国省道在汛期容易受边坡风险影响。",
            },
            {
                "heading": "能源与市政",
                "body": "全市电力供应以省网和本地火电联供为主，工业蒸汽管网集中在北山、临江园区。两个城区供水总体有保障，但部分老旧片区雨污分流和排涝能力不足。",
            },
            {
                "heading": "防灾体系",
                "body": "市级建有综合应急指挥平台，各县区分别储备防汛、消防和救灾物资。公开预案明确属地先期处置、行业部门专业支撑和市级统筹调度，但跨部门演练与物资台账仍需定期核验。",
            },
        ],
        "source_note": "虚构资料，综合交通规划、城市建设公报和综合防灾规划形成。",
    },
    {
        "id": "ref-nanchuan",
        "category": "县区概况",
        "title": "南川区基本情况",
        "subtitle": "中心城区、河谷商贸与装备制造",
        "updated_date": "2025-12",
        "summary": "南川区常住人口约七十六万，是市委、市政府驻地，也是南川河穿城段防汛和老城更新的重点区域。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖十二个街道、四个乡镇，常住人口约七十六万。人口和公共服务高度集中于河谷主城区，西北部仍有丘陵乡镇。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约五百零二亿元，一般公共预算收入约四十三亿元。商贸服务、总部经济、装备制造和城市建设是主要支撑，区级支出同时承担较多中心城区公共服务。",
            },
            {
                "heading": "公开关注点",
                "body": "南川河穿城段、老旧小区排涝、城中村改造和教育医疗承载压力长期受到关注。公开材料将防汛标准提升列入近年重点项目。",
            },
        ],
        "source_note": "虚构县区公开概况，不包含内部排查、未报送台账或个人判断。",
    },
    {
        "id": "ref-linjiang",
        "category": "县区概况",
        "title": "临江区基本情况",
        "subtitle": "老工业城区、港站物流与城市更新",
        "updated_date": "2025-12",
        "summary": "临江区常住人口约六十二万，老工业片区和区域物流枢纽并存，转型与更新任务较重。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖九个街道、五个乡镇，常住人口约六十二万。城区沿铁路和澄江支流展开，老厂区、铁路生活区和新物流片区交错。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约四百八十六亿元，一般公共预算收入约三十六亿元。装备制造、基础化工、仓储物流和生产性服务业占比较高。",
            },
            {
                "heading": "公开关注点",
                "body": "老工业用地再开发、土壤治理、国企退休人员服务和老旧管网改造是持续议题，物流园扩建也带来交通组织压力。",
            },
        ],
        "source_note": "虚构县区公开概况，不包含尚未公开的项目谈判和企业经营信息。",
    },
    {
        "id": "ref-beishan",
        "category": "县区概况",
        "title": "北山县基本情况",
        "subtitle": "资源型县域、焦化产业与丘陵农业",
        "updated_date": "2025-12",
        "summary": "北山县常住人口约七十一万，焦化及上下游是财政与就业的重要支柱，产业集中度较高。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖三个街道、十四个乡镇，常住人口约七十一万。县城和北山产业园吸纳主要非农就业，外围丘陵乡镇以粮油、养殖和外出务工为主。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约四百二十三亿元，一般公共预算收入约二十八亿元、支出约七十一亿元。焦化、煤化工配套和运输服务占工业比重较高，县级财力容易受企业利润和环保限产影响。",
            },
            {
                "heading": "公开关注点",
                "body": "产业绿色改造、园区空气质量、劳务用工和资源型地区转型是公开政策重点。县里已多次提出争取省市技改、稳岗和园区基础设施支持。",
            },
        ],
        "source_note": "虚构县区公开概况；具体就业名单、欠付奖补和企业现金流不属于本材料。",
    },
    {
        "id": "ref-dongning",
        "category": "县区概况",
        "title": "东宁市基本情况",
        "subtitle": "县级市、平原农业与加工制造",
        "updated_date": "2025-12",
        "summary": "东宁市常住人口约六十六万，是岚州东部交通节点和商品粮、食品加工基地。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖五个街道、十三个乡镇，常住人口约六十六万。地势较平缓，城镇和规模农业沿铁路、高速公路分布。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约三百六十八亿元，一般公共预算收入约二十三亿元。农产品加工、轻型装备、纺织和县域商贸较为活跃。",
            },
            {
                "heading": "公开关注点",
                "body": "粮食产能、高标准农田、食品加工园扩能和中小企业融资是重点，部分乡镇还面临地下水利用和农业面源污染压力。",
            },
        ],
        "source_note": "虚构县区公开概况，不包含企业个别授信和项目评审意见。",
    },
    {
        "id": "ref-qingyuan",
        "category": "县区概况",
        "title": "青源县基本情况",
        "subtitle": "西部山区、生态农业与水源涵养",
        "updated_date": "2025-12",
        "summary": "青源县常住人口约五十五万，生态保护面积大，县域发展依赖特色农业、文旅和转移支付。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖两个街道、十五个乡镇，常住人口约五十五万。村庄分散、山地交通半径较长，人口老龄化和劳动力外流较明显。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约二百一十五亿元，一般公共预算收入约十二亿元。茶叶、中药材、林产品和生态旅游是主要特色，县级基本公共服务较依赖转移支付。",
            },
            {
                "heading": "公开关注点",
                "body": "水源涵养、地质灾害、农村道路和乡镇医疗教育是长期任务。发展项目需要同时满足生态保护和群众增收要求。",
            },
        ],
        "source_note": "虚构县区公开概况，不包含生态项目审批中的内部意见。",
    },
    {
        "id": "ref-hezhou",
        "category": "县区概况",
        "title": "和州县基本情况",
        "subtitle": "南部农业县、劳务输出与基础民生",
        "updated_date": "2025-12",
        "summary": "和州县常住人口约四十八万，经济体量较小，农业、劳务输出和基础民生保障占据较大政策权重。",
        "sections": [
            {
                "heading": "人口与空间",
                "body": "辖一个街道、十二个乡镇，常住人口约四十八万。南部平坝是粮食和畜牧主产区，边缘乡镇交通与公共服务可达性较弱。",
            },
            {
                "heading": "经济与财政",
                "body": "地区生产总值约一百五十四亿元，一般公共预算收入约九亿元。粮油、畜牧、服装加工和劳务经济是主要支撑，县级财政以保基本民生和基层运转为先。",
            },
            {
                "heading": "公开关注点",
                "body": "乡村学校布局、县域医疗、农田水利和返乡就业是主要议题。人口老龄化使养老服务和基层照护需求持续上升。",
            },
        ],
        "source_note": "虚构县区公开概况，不包含具体补助分配和未公开项目储备。",
    },
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
    "nanchuan_secretary": {
        "name": "杜行舟",
        "title": "南川区委书记",
        "public_position": "主张尽快复核南川河险段，但希望市级明确工程和物资支持边界。",
        "known_note": "掌握南川区防汛组织和属地工程情况，近期材料与现场照片存在差异。",
        "work_style": "熟悉基层工程，汇报谨慎，会区分已经验收、当前可用和仍需复核的状态。",
        "private_goal": "在汛期前补齐真实短板，同时避免把历史验收问题和全部资金责任压给南川区。",
        "beliefs": [
            {
                "id": "nanchuan_acceptance_gap",
                "content": "区里所称的“已完成修复”沿用了去年项目验收结论，尚未覆盖今年发现的冲刷点。",
                "source": "南川区汛前内部复查记录",
            },
            {
                "id": "nanchuan_material_shortage",
                "content": "属地现有可立即调用的合格沙袋和照明设备低于报表数，补充采购尚未到货。",
                "source": "区防指物资抽查台账",
            },
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


ACTORS.update(
    {
        "linjiang_secretary": {
            "name": "贾闻澜",
            "title": "临江区委书记",
            "public_position": "主张把老工业区更新与产业承接统筹推进，反对只拆不建。",
            "known_note": "熟悉老工业片区、国企社区和物流园，协调城市更新经验较多。",
            "work_style": "善于跨部门协调，公开表达稳健，涉及土地和国企历史问题时格外谨慎。",
            "private_goal": "争取市级支持完成片区转型，同时避免历史环境成本全部由区级财政承担。",
            "beliefs": [
                {
                    "id": "linjiang_brownfield_cost",
                    "content": "临江老厂区首期土壤治理的内部测算比公开项目估算高约三成，尚未落实完整资金来源。",
                    "source": "临江区城市更新专班底稿",
                }
            ],
        },
        "dongning_secretary": {
            "name": "李衍初",
            "title": "东宁市委书记",
            "public_position": "希望以农产品加工和交通区位扩大县域就业，强调项目要尽快落地。",
            "known_note": "掌握东部平原农业、食品加工园和县域中小企业情况。",
            "work_style": "目标感强、重项目进度，愿意竞争资源，但会维护县级市的自主安排。",
            "private_goal": "把食品加工园列入市级重点盘子，并证明东宁不只是传统农业县域。",
            "beliefs": [
                {
                    "id": "dongning_processing_gap",
                    "content": "食品加工园二期已有企业意向，但污水处理扩容和冷链用地尚未完成要素闭合。",
                    "source": "东宁市项目调度会内部清单",
                }
            ],
        },
        "qingyuan_secretary": {
            "name": "石静川",
            "title": "青源县委书记",
            "public_position": "坚持生态底线，也要求生态保护成本在市级项目和转移支付中得到体现。",
            "known_note": "熟悉山区乡镇、生态农业和水源保护，基层公共服务压力较大。",
            "work_style": "说话平缓但守边界，习惯把生态、民生和财力约束放在一起谈。",
            "private_goal": "守住生态考核和基层运转，避免县里承担保护责任却持续失去人口和产业。",
            "beliefs": [
                {
                    "id": "qingyuan_road_risk",
                    "content": "两条山区公路在近期巡查中发现边坡变形，但县级养护资金只能先覆盖其中一处。",
                    "source": "青源县交通与地灾联合巡查记录",
                }
            ],
        },
        "hezhou_secretary": {
            "name": "宋知衡",
            "title": "和州县委书记",
            "public_position": "主张把有限资金优先用于基层民生、农田水利和返乡就业。",
            "known_note": "长期在农业县工作，对乡镇运转、教育医疗和劳务输出较熟悉。",
            "work_style": "务实低调，不热衷大项目，面对资源竞争会反复强调基本民生底线。",
            "private_goal": "确保县级财政不断链，并让市里看见人口小县承担的基本公共服务成本。",
            "beliefs": [
                {
                    "id": "hezhou_school_transport",
                    "content": "和州拟撤并的三所乡村学校涉及较长通学距离，现有校车和寄宿条件不足以直接承接。",
                    "source": "和州县教育布局内部评估",
                }
            ],
        },
        "finance_director": {
            "name": "叶秋实",
            "title": "市财政局局长",
            "public_position": "新增政策先算财力、期限和退出机制，不能把意向写成财政兜底。",
            "known_note": "掌握预算、转移支付、政府债务和市县财政运行，是资金边界的直接信息源。",
            "work_style": "谨慎精确，习惯区分预算安排、资金测算、债务责任和支付进度。",
            "private_goal": "保住基本民生和财政运行底线，同时避免财政局替未经决策的方案背书。",
            "beliefs": [
                {
                    "id": "finance_competing_requests",
                    "content": "各部门近期新增支出诉求合计约十三点八亿元，而年内可重新统筹的市级财力初测约六点二亿元。",
                    "source": "财政局滚动平衡测算",
                }
            ],
        },
        "development_reform_director": {
            "name": "俞敬川",
            "title": "市发展和改革委员会主任",
            "public_position": "重大项目应先做必要性、要素和资金闭合，再决定进入哪一层项目盘子。",
            "known_note": "掌握全市规划、重大项目、投资审批和经济运行调度。",
            "work_style": "擅长把政治目标转成项目条件，面对不成熟项目会留下明确前置项。",
            "private_goal": "提升项目成熟度和争取上级资金的命中率，避免项目清单只增不减。",
            "beliefs": [
                {
                    "id": "development_project_maturity",
                    "content": "当前拟争取省级支持的八个重点项目中，有三个尚未同时落实用地、资本金和运营主体。",
                    "source": "市发改委重大项目要素清单",
                }
            ],
        },
        "industry_bureau_director": {
            "name": "郑其峰",
            "title": "市工业和信息化局局长",
            "public_position": "产业整改要分生产线、企业和时间窗口，不能把全行业写成一个结论。",
            "known_note": "掌握工业运行、技改项目、重点企业调度和产业链就业估算。",
            "work_style": "数据密集、重连续生产，倾向用分阶段技术方案减少停产冲击。",
            "private_goal": "维持工业基本盘并推动真实技改，避免工信系统继续为企业未兑现承诺背书。",
            "beliefs": [
                {
                    "id": "industry_employment_estimate",
                    "content": "按重点企业、劳务派遣和稳定上下游三类口径合并，工信局内部估计北山直接相关就业约九千八百人。",
                    "source": "市工信局企业运行调度表",
                }
            ],
        },
        "human_resources_director": {
            "name": "冯雅萍",
            "title": "市人力资源和社会保障局局长",
            "public_position": "稳岗和安置必须以可核验人员为基础，同时不能遗漏派遣工和实际就业人员。",
            "known_note": "掌握就业、社保、劳动关系和职业培训渠道，可组织人员名单核验。",
            "work_style": "重视个体权益和名单证据，会区分劳动合同、社保记录与实际用工。",
            "private_goal": "让稳岗政策覆盖真实受影响者，并防止模糊名单造成资金错配和劳动争议。",
            "beliefs": [
                {
                    "id": "human_resources_roster_gap",
                    "content": "跨库比对发现约一千九百名劳务派遣和承包用工没有进入北山县正式稳岗名单。",
                    "source": "市人社局就业与社保数据比对",
                }
            ],
        },
        "water_director": {
            "name": "陆汝成",
            "title": "市水利局局长",
            "public_position": "防汛风险等级必须以复核和工程现状为准，不能沿用过期验收结论。",
            "known_note": "掌握河道、水库、水利工程和防汛技术资料，是险段专业责任部门。",
            "work_style": "专业保守，重设计标准、现场复核和上下游联动，避免口头判断替代技术结论。",
            "private_goal": "尽快消除关键险段的不确定性，并明确工程维护、属地巡查和市级调度责任。",
            "beliefs": [
                {
                    "id": "water_design_gap",
                    "content": "南川河争议险段现有临时加固只按常遇洪水工况施工，没有覆盖最新复核提出的冲刷深度。",
                    "source": "市水利局技术复核底稿",
                }
            ],
        },
        "emergency_director": {
            "name": "邓闻达",
            "title": "市应急管理局局长",
            "public_position": "预案、队伍和物资要在同一场景下验证，台账数量不等于现场可调用能力。",
            "known_note": "掌握综合应急协调、危险化学品安全和跨部门救援资源。",
            "work_style": "强调最坏情形和响应链，会追问物资在哪里、谁能调、多久能到。",
            "private_goal": "补齐跨部门联动短板，但避免应急部门替行业主管部门承担全部日常治理责任。",
            "beliefs": [
                {
                    "id": "emergency_stock_transfer",
                    "content": "市级账面防汛物资中约三成存放在北部仓库，若南川河突发险情，夜间转运至少需要四小时。",
                    "source": "市应急局物资调运推演",
                }
            ],
        },
        "state_assets_director": {
            "name": "范景泰",
            "title": "市国有资产监督管理委员会主任",
            "public_position": "市属国企可以承担符合主业和程序的任务，但不能被当作无成本财政工具。",
            "known_note": "掌握市属国企资产、负债、主业和投资决策边界。",
            "work_style": "重资产穿透和董事会程序，愿意研究方案，但反对口头指定交易。",
            "private_goal": "维护国有资本安全和企业持续经营，同时争取在城市转型中发挥作用。",
            "beliefs": [
                {
                    "id": "state_assets_capacity",
                    "content": "具备产业投资经验的两家市属企业中，只有一家尚有一定融资空间，但其现金流已承担在建基础设施项目。",
                    "source": "市国资委月度财务监测",
                }
            ],
        },
        "audit_director": {
            "name": "段谨言",
            "title": "市审计局局长",
            "public_position": "重大资金安排应当留有依据、绩效目标和完整流向，历史问题也不能靠新项目覆盖。",
            "known_note": "掌握财政资金、国企和政府投资审计方法，但不替纪检监察机关作定性。",
            "work_style": "按证据说话，区分管理不规范、绩效不足和需要移送的线索。",
            "private_goal": "让高风险方案在实施前暴露控制缺口，避免事后只能追溯无法挽回的损失。",
            "beliefs": [
                {
                    "id": "audit_unsettled_funds",
                    "content": "北山产业园以前年度有两千二百万元专项资金长期挂在往来科目，尚未完成项目和资产对应核销。",
                    "source": "市审计局审前数据分析",
                }
            ],
        },
        "natural_resources_director": {
            "name": "方同甫",
            "title": "市自然资源和规划局局长",
            "public_position": "项目用地、规划用途和存量资产必须对应，不能以规划意向替代合法手续。",
            "known_note": "掌握土地、规划、矿产、地灾和不动产登记信息。",
            "work_style": "程序边界清楚，善于发现同一资产在规划、抵押和项目方案中的不同口径。",
            "private_goal": "盘活存量用地但守住规划和资产真实性，避免部门被迫为既定交易补手续。",
            "beliefs": [
                {
                    "id": "natural_resources_mortgage_overlap",
                    "content": "北岭能源拟注入重组方案的两宗核心工业用地已有抵押登记，且其中一宗涉及用途调整。",
                    "source": "不动产登记与项目用地核对记录",
                }
            ],
        },
        "housing_director": {
            "name": "徐曼宁",
            "title": "市住房和城乡建设局局长",
            "public_position": "城市更新要先补安全和市政短板，再平衡开发强度与资金回收。",
            "known_note": "掌握住房、城市建设、燃气和排水管网项目。",
            "work_style": "重现场条件和工程时序，对只有概念图、没有运维安排的项目保持警惕。",
            "private_goal": "优先处理安全和排涝短板，同时避免城市更新形成新的停工和隐性债务风险。",
            "beliefs": [
                {
                    "id": "housing_drainage_gap",
                    "content": "南川、临江共有二十三个老旧小区在强降雨条件下可能出现排水倒灌，其中九个尚未纳入已落实资金的改造计划。",
                    "source": "市住建局排水防涝排查台账",
                }
            ],
        },
        "transport_director": {
            "name": "季航",
            "title": "市交通运输局局长",
            "public_position": "产业运输和山区保通要统筹施工窗口，不能让多个项目同时切断替代通道。",
            "known_note": "掌握干线公路、客货运输和交通建设养护安排。",
            "work_style": "调度意识强，重时段、绕行能力和运输成本，倾向先做可执行排程。",
            "private_goal": "保证工业和民生运输基本畅通，同时争取补足长期欠账的养护资金。",
            "beliefs": [
                {
                    "id": "transport_corridor_overlap",
                    "content": "北山货运走廊两座桥梁的维修窗口与汛期和园区设备运输计划重叠，现有绕行线路难以承受全部重载车辆。",
                    "source": "市交通运输局施工组织内部评估",
                }
            ],
        },
        "agriculture_director": {
            "name": "罗青禾",
            "title": "市农业农村局局长",
            "public_position": "产业和防灾安排都要看到县域农业、农民收入和村级执行成本。",
            "known_note": "掌握粮食生产、乡村产业、农田建设和农业防灾情况。",
            "work_style": "重基层样本和季节窗口，会提醒城市部门不要把农村影响写成附带事项。",
            "private_goal": "守住粮食和农民收入底线，并让农业项目不再长期为工业项目让位。",
            "beliefs": [
                {
                    "id": "agriculture_flood_exposure",
                    "content": "南川河下游约四点二万亩农田依赖三处排涝站，其中一处主泵检修尚未完成。",
                    "source": "市农业农村局春季生产调度",
                }
            ],
        },
        "health_director": {
            "name": "王执中",
            "title": "市卫生健康委员会主任",
            "public_position": "医疗资源配置要同时考虑城区承载、县域急救和公共卫生韧性。",
            "known_note": "掌握全市医疗机构、疾控、急救和基层卫生资源。",
            "work_style": "风险意识强，重专业能力和服务半径，不愿用床位总数掩盖结构短板。",
            "private_goal": "提升县域急救和基层服务能力，同时控制公立医院运行风险。",
            "beliefs": [
                {
                    "id": "health_hospital_arrears",
                    "content": "三家县级公立医院的药品耗材应付款持续上升，其中一家现金保障只能维持约两个月。",
                    "source": "市卫健委公立医院运行监测",
                }
            ],
        },
        "education_director": {
            "name": "薛含章",
            "title": "市教育局局长",
            "public_position": "学校布局应跟随真实人口变化，城区扩容与乡村教育底线都不能只靠短期调剂。",
            "known_note": "掌握基础教育学位、教师队伍和职业教育资源。",
            "work_style": "重长期人口趋势和公平，面对临时性指标任务时会要求说明持续成本。",
            "private_goal": "缓解城区学位压力并稳定薄弱地区教师队伍，避免校舍项目挤占长期师资投入。",
            "beliefs": [
                {
                    "id": "education_capacity_gap",
                    "content": "南川区未来两年小学净增学位需求约四千个，但已落实建设计划只能提供约二千六百个。",
                    "source": "市教育局学龄人口滚动测算",
                }
            ],
        },
        "petitions_director": {
            "name": "孔亦秋",
            "title": "市信访局局长",
            "public_position": "重复诉求要区分合理诉求、程序堵点和历史积案，不能只以是否进京赴省衡量风险。",
            "known_note": "掌握跨部门信访事项、重复访和基层矛盾流转情况。",
            "work_style": "耐心细致，重问题来源和责任单位，反对用临时稳控替代实体解决。",
            "private_goal": "推动一批长期积案真正解决，同时避免信访部门成为所有部门拖延后的最后兜底者。",
            "beliefs": [
                {
                    "id": "petitions_repeated_cases",
                    "content": "近期十七件重复来访中，有六件与北山劳务工资或历史奖补有关，责任单位的答复口径并不一致。",
                    "source": "市信访局重复事项分析",
                }
            ],
        },
        "public_security_director": {
            "name": "赵启原",
            "title": "副市长、市公安局局长",
            "public_position": "依法维护秩序必须建立在风险研判和实质化解基础上，不能把一般劳动诉求先行定性。",
            "known_note": "掌握治安、交通和重大活动安全信息，与政法委共同关注社会风险。",
            "work_style": "重预案和证据，行动果断，但会明确公安处置不能替代行业部门解决欠薪和合同问题。",
            "private_goal": "防止矛盾升级为公共安全事件，同时保持执法边界和警力可持续。",
            "beliefs": [
                {
                    "id": "public_security_contractors",
                    "content": "北山园区两家承包商近期咨询集体讨薪报备事宜，但目前没有发现暴力或跨区域组织迹象。",
                    "source": "市公安局基层警情与走访汇总",
                }
            ],
        },
    }
)


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
        "author_id": "finance_director",
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
        "author_id": "water_director",
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
    "nanchuan_secretary": "南川区会先复核险段和物资，但请把去年验收结论、今年新发现的问题和新增资金责任分开记录，不能用一句‘已经修复’概括。",
    "environment_director": "二号线检修是一个真实窗口。只要尽快固定停产范围和监测节点，可以降低后续整改成本。",
    "chairman": "企业愿意整改，但如果政策信号是强制并购，订单和技术团队都不可能原地等待。",
    "banker": "分行可以继续评估，前提是资产穿透和现金流真实。政策信号不能替代省行审批。",
    "superior": "我关心的不是材料写得多完整，而是岚州是否掌握真实情况、形成责任清楚且能执行的安排。",
}


TEMPLATE_UTTERANCES.update(
    {
        "linjiang_secretary": "临江愿意承担老工业区更新任务，但污染治理、土地处置和社区安置必须放在同一张责任表上，不能只给开发时点。",
        "dongning_secretary": "东宁的项目有市场和就业基础，但污水、冷链和用地条件还要闭合。市里若列为重点，请同步明确前置条件。",
        "qingyuan_secretary": "青源会守住生态底线，但保护成本和基层服务不能长期只由县里消化。项目取舍应把转移支付和群众增收一并考虑。",
        "hezhou_secretary": "和州最关心的是基本民生和乡镇执行能力。大项目可以竞争，但不能因此挤掉农田水利、学校和县域医疗的刚性支出。",
        "finance_director": "财政可以测算不同方案，但必须区分可统筹财力、专项资金和需要后续年度承担的责任，不能先承诺再找账。",
        "development_reform_director": "建议先把项目必要性、要素保障和资金闭合列清。进入项目清单不等于取得审批或资金。",
        "industry_bureau_director": "产业整改要落到生产线、技改节点和企业责任。就业影响也应分别核对直接用工、派遣用工和稳定上下游。",
        "human_resources_director": "稳岗和安置首先要有可核验名单。劳动合同、社保记录和实际用工不完全重合，不能只采用最窄口径。",
        "water_director": "水利技术结论要以当前工程状态和复核标准为准。去年的验收可以作为资料，但不能替代今年的险情判断。",
        "emergency_director": "应急准备不能只看台账总量，还要看存放地点、调运时间、专业队伍和夜间响应链是否真的可用。",
        "state_assets_director": "市属国企可以研究参与，但必须符合主业、资产评估和投资程序。政策任务不能被写成没有成本的企业自愿行为。",
        "audit_director": "建议在方案形成时同步明确资金依据、绩效目标和流向记录。审计可以提示风险，但不会在证据不足时替其他机关定性。",
        "natural_resources_director": "土地用途、权属、抵押和规划条件需要逐项核对。概念方案不能替代用地和资产手续。",
        "housing_director": "城市建设要先确认安全短板、工程时序和长期运维。只有建设规模、没有排水和资金闭环的方案难以执行。",
        "transport_director": "请把施工窗口、重载运输和替代路线放在同一张图上。多个项目同时开工可能让产业和民生运输都受影响。",
        "agriculture_director": "防汛和项目排序也会影响农时、农田和农民收入。县域农业不能只作为工业方案的附带影响处理。",
        "health_director": "医疗资源不能只看全市床位总数，还要看县域急救、专科能力和医院现金运行能否支撑。",
        "education_director": "学校布局应依据真实学龄人口和通学条件。建校、师资和长期运行成本需要一起进入方案。",
        "petitions_director": "重复来访背后可能是程序堵点，也可能是实体问题长期未解。建议先统一责任单位的事实和答复口径。",
        "public_security_director": "公安会依法维护秩序并做好预案，但劳动、合同和行业治理问题仍需责任部门实质化解，不能先行安全化。",
    }
)


ACTOR_DIRECTORY_GROUPS = {
    "mayor": "市级班子",
    "secretary_general": "市级班子",
    "fulltime_deputy": "市级班子",
    "executive_vice_mayor": "市级班子",
    "industry_vice_mayor": "市级班子",
    "discipline": "市级班子",
    "organization_minister": "市级班子",
    "propaganda_minister": "市级班子",
    "political_legal_secretary": "市级班子",
    "united_front_minister": "市级班子",
    "garrison_commissar": "市级班子",
    "county_secretary": "县区主官",
    "nanchuan_secretary": "县区主官",
    "environment_director": "市直部门",
    "chairman": "企业与金融",
    "banker": "企业与金融",
    "superior": "上级",
}


ACTOR_DIRECTORY_GROUPS.update(
    {
        "linjiang_secretary": "县区主官",
        "dongning_secretary": "县区主官",
        "qingyuan_secretary": "县区主官",
        "hezhou_secretary": "县区主官",
        "finance_director": "市直部门",
        "development_reform_director": "市直部门",
        "industry_bureau_director": "市直部门",
        "human_resources_director": "市直部门",
        "water_director": "市直部门",
        "emergency_director": "市直部门",
        "state_assets_director": "市直部门",
        "audit_director": "市直部门",
        "natural_resources_director": "市直部门",
        "housing_director": "市直部门",
        "transport_director": "市直部门",
        "agriculture_director": "市直部门",
        "health_director": "市直部门",
        "education_director": "市直部门",
        "petitions_director": "市直部门",
        "public_security_director": "市级班子",
    }
)


CITY_INSIDER_GROUPS = {"市级班子", "县区主官", "市直部门"}
EXTERNAL_STAKEHOLDER_IDS = {"chairman", "banker"}

# These links describe whom an external or provincial actor is expected to know
# personally. Municipal leaders, county principals and bureau heads receive the
# full municipal public roster because they work inside the same cadre and
# coordination system; the entries never include another actor's private goal or
# beliefs.
ACTOR_STAKEHOLDER_LINKS = {
    "chairman": [
        "player",
        "mayor",
        "secretary_general",
        "executive_vice_mayor",
        "industry_vice_mayor",
        "county_secretary",
        "environment_director",
        "finance_director",
        "development_reform_director",
        "industry_bureau_director",
        "human_resources_director",
        "state_assets_director",
        "banker",
    ],
    "banker": [
        "player",
        "mayor",
        "secretary_general",
        "executive_vice_mayor",
        "industry_vice_mayor",
        "county_secretary",
        "finance_director",
        "development_reform_director",
        "state_assets_director",
        "audit_director",
        "natural_resources_director",
        "chairman",
    ],
    "superior": [item for item in STANDING_COMMITTEE_MEMBER_IDS],
}


ACTOR_SUPERVISOR_IDS = {
    "mayor": ["player", "superior"],
    "fulltime_deputy": ["player"],
    "secretary_general": ["player"],
    "executive_vice_mayor": ["player", "mayor"],
    "industry_vice_mayor": ["player", "mayor"],
    "discipline": ["player"],
    "organization_minister": ["player"],
    "propaganda_minister": ["player"],
    "political_legal_secretary": ["player"],
    "united_front_minister": ["player"],
    "garrison_commissar": ["player"],
    "public_security_director": ["player", "mayor", "political_legal_secretary"],
    "finance_director": ["mayor", "executive_vice_mayor"],
    "development_reform_director": ["mayor", "executive_vice_mayor"],
    "state_assets_director": ["mayor", "executive_vice_mayor"],
    "audit_director": ["mayor", "executive_vice_mayor"],
    "natural_resources_director": ["mayor", "executive_vice_mayor"],
    "industry_bureau_director": ["mayor", "industry_vice_mayor"],
    "human_resources_director": ["mayor", "industry_vice_mayor"],
    "environment_director": ["mayor", "industry_vice_mayor"],
    "water_director": ["mayor"],
    "emergency_director": ["mayor"],
    "housing_director": ["mayor"],
    "transport_director": ["mayor"],
    "agriculture_director": ["mayor"],
    "health_director": ["mayor"],
    "education_director": ["mayor"],
    "petitions_director": ["player", "political_legal_secretary"],
    "county_secretary": ["player", "mayor"],
    "nanchuan_secretary": ["player", "mayor"],
    "linjiang_secretary": ["player", "mayor"],
    "dongning_secretary": ["player", "mayor"],
    "qingyuan_secretary": ["player", "mayor"],
    "hezhou_secretary": ["player", "mayor"],
    "chairman": ["county_secretary", "industry_vice_mayor"],
    "banker": ["superior"],
    "superior": [],
}


def actor_acquaintance_ids(actor_id: str) -> List[str]:
    """Return the public people roster that this actor can identify and reason about."""
    if actor_id not in ACTORS:
        raise KeyError(actor_id)
    group = ACTOR_DIRECTORY_GROUPS[actor_id]
    if group in CITY_INSIDER_GROUPS:
        candidates = ["player", "superior"] + [
            item_id
            for item_id in ACTORS
            if ACTOR_DIRECTORY_GROUPS[item_id] in CITY_INSIDER_GROUPS
        ]
        candidates.extend(EXTERNAL_STAKEHOLDER_IDS)
    else:
        candidates = list(ACTOR_STAKEHOLDER_LINKS.get(actor_id, ["player"]))
    if actor_id in ACTOR_SUPERVISOR_IDS:
        candidates.extend(ACTOR_SUPERVISOR_IDS[actor_id])
    return list(dict.fromkeys(item for item in candidates if item != actor_id))


def actor_organizational_relationship(observer_id: str, target_id: str) -> str:
    if target_id in ACTOR_SUPERVISOR_IDS.get(observer_id, []):
        return "上级或主要汇报对象"
    if observer_id in ACTOR_SUPERVISOR_IDS.get(target_id, []):
        return "分管或联系范围内的下级"
    if observer_id in STANDING_COMMITTEE_MEMBER_IDS and target_id in STANDING_COMMITTEE_MEMBER_IDS:
        return "市委常委班子同事"
    if target_id in EXTERNAL_STAKEHOLDER_IDS or observer_id in EXTERNAL_STAKEHOLDER_IDS:
        return "工作利益相关方"
    if target_id == "superior":
        return "省级上级"
    return "同一地方治理网络中的工作联系人"


def actor_context(actor_id: str) -> Dict[str, Any]:
    if actor_id not in ACTORS:
        raise KeyError(actor_id)
    return {"id": actor_id, **deepcopy(ACTORS[actor_id])}


def actor_belief_ids(actor_id: str) -> List[str]:
    return [item["id"] for item in ACTORS[actor_id]["beliefs"]]


def public_reference_ids() -> List[str]:
    return [item["id"] for item in PUBLIC_REFERENCE_MATERIALS]


def actor_knowledge_ids(actor_id: str) -> List[str]:
    return actor_belief_ids(actor_id) + public_reference_ids()


def actor_label(actor_id: str) -> str:
    if actor_id == "player":
        return "市委书记"
    actor = ACTORS.get(actor_id)
    return actor["name"] if actor else actor_id
