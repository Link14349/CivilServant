import random
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ActorView,
    ConversationView,
    DossierView,
    GameView,
    HistoryEntryView,
    MetricView,
    OptionView,
    OutcomeView,
    ParsedAction,
    ParsedConversation,
    PrivateRecordView,
    ReportView,
    ResponsibilityView,
    StoredGame,
    TurnView,
)
from .scenario import (
    ACTORS,
    EFFECTS,
    METRIC_DEFINITIONS,
    TEMPLATE_NARRATIVES,
    TEMPLATE_REACTIONS,
    TEMPLATE_INQUIRY,
    actor_belief_ids,
    allowed_tags,
    initial_state,
    option_by_id,
    responsibility_for_tag,
    turn_definition,
)


DEFAULT_CUSTOM_TAGS = [
    "mayor_compliance",
    "phased_plan",
    "balanced_bargain",
    "record_dissent",
    "acknowledge_adjust",
    "transparent_review",
]


def create_game(
    player_name: str,
    mode: str,
    model: str,
    api_base: str,
    seed: Optional[int] = None,
) -> StoredGame:
    game_seed = seed or random.SystemRandom().randint(1, 2_147_483_647)
    return StoredGame(
        id=str(uuid.uuid4()),
        version=1,
        player_name=player_name.strip(),
        mode=mode,
        model=model,
        api_base=api_base.rstrip("/"),
        seed=game_seed,
        turn_index=0,
        status="active",
        state=initial_state(),
        history=[],
    )


def template_action(
    game: StoredGame,
    option_id: Optional[str],
    custom_text: Optional[str],
) -> Tuple[ParsedAction, str]:
    if option_id:
        option = option_by_id(game.turn_index, option_id)
        tag = option_id
        summary = option["directive"]
        choice = option["label"]
    else:
        text = (custom_text or "").strip()
        tag = classify_template_custom(game.turn_index, text)
        summary = "你的指令被理解为：{}".format(text)
        choice = "其他：{}".format(_shorten(text, 34))

    reactions = deepcopy(TEMPLATE_REACTIONS.get(tag, []))
    narrative = TEMPLATE_NARRATIVES.get(tag, "相关单位开始按照你的方向重新组织材料和行动。")
    return (
        ParsedAction(
            strategy_tag=tag,
            directive_summary=summary,
            narrative=narrative,
            npc_reactions=reactions,
        ),
        choice,
    )


def classify_template_custom(turn_index: int, text: str) -> str:
    keyword_maps = [
        [
            ("延期", "delay_for_jobs"),
            ("亲自", "personal_taskforce"),
            ("专班", "personal_taskforce"),
            ("市长", "mayor_compliance"),
        ],
        [
            ("国企", "state_owned_merge"),
            ("企业自", "enterprise_self_rescue"),
            ("亲自", "personal_control"),
            ("分期", "phased_plan"),
        ],
        [
            ("银行", "credit_signal"),
            ("不承诺", "hard_line"),
            ("无条件", "hard_line"),
            ("名单", "conditional_support"),
            ("分段", "balanced_bargain"),
        ],
        [
            ("退回", "defer_decision"),
            ("暂缓", "defer_decision"),
            ("直接", "executive_order"),
            ("统一口径", "unify_and_press"),
            ("记录", "record_dissent"),
        ],
        [
            ("换人", "replace_lead"),
            ("追责", "replace_lead"),
            ("省里", "seek_province"),
            ("不变", "double_down"),
            ("纠偏", "acknowledge_adjust"),
            ("承认", "acknowledge_adjust"),
        ],
        [
            ("县里", "blame_county"),
            ("基层", "blame_county"),
            ("担责", "accept_responsibility"),
            ("突出成绩", "polish_report"),
            ("如实", "transparent_review"),
            ("问题", "transparent_review"),
        ],
    ]
    for keyword, tag in keyword_maps[turn_index]:
        if keyword in text:
            return tag
    return DEFAULT_CUSTOM_TAGS[turn_index]


def template_conversation(
    game: StoredGame,
    actor_id: str,
    channel: str,
    intent: str,
    message: str,
) -> ParsedConversation:
    actor = ACTORS[actor_id]
    if intent == "inquire":
        template = TEMPLATE_INQUIRY[actor_id]
        reply = template["reply"]
        if channel == "written_inquiry":
            reply = "书面答复：{}".format(reply)
        return ParsedConversation(
            reply=reply,
            disposition="inform" if channel == "private_meeting" else "cautious",
            used_belief_ids=template["used_belief_ids"],
            consequence_note=template["consequence_note"],
        )

    if intent == "sound_out":
        return ParsedConversation(
            reply="书记，我理解您是在了解态度。就我的职责看，{} 但在方案、资金和责任边界明确前，我不会把这理解成正式决定。".format(
                actor["public_position"]
            ),
            disposition="cautious",
            used_belief_ids=[],
            consequence_note="你获得了对方的原则态度，但双方都没有形成承诺。",
        )

    if intent == "private_assignment":
        if actor_id in {"chairman", "banker"}:
            return ParsedConversation(
                reply="这件事涉及政府内部职责，我可以按本机构权限配合提供材料，但不能接受市委对内部工作的秘密交办。",
                disposition="decline",
                used_belief_ids=[],
                consequence_note="对方拒绝接受超出其组织关系的秘密交办。",
            )
        major_keywords = ("关停", "拨款", "担保", "并购", "任命", "处分", "免职", "土地")
        if any(keyword in message for keyword in major_keywords):
            return ParsedConversation(
                reply="我可以先摸底、准备材料，但这件事不能只靠我们这次谈话生效。需要把依据和责任边界做实，再走会议或相应程序。",
                disposition="needs_formalization",
                used_belief_ids=[],
                commitment_summary="{}先行准备：{}".format(actor["name"], _shorten(message, 90)),
                requires_formal_decision=True,
                consequence_note="对方只接受前期准备，重大事项仍待正式决策。",
            )
        return ParsedConversation(
            reply="我明白。这项工作先不扩大知情范围，我按职责摸清情况、形成一份可供您判断的材料；如果需要跨部门执行，再请您正式授权。",
            disposition="accept",
            used_belief_ids=[],
            commitment_summary="{}私下承接：{}".format(actor["name"], _shorten(message, 90)),
            consequence_note="形成一项有限范围的非正式交办。",
        )

    if actor_id == "county_secretary":
        return ParsedConversation(
            reply="如果市里明确先核名单、再按核实人数安排培训和项目，我可以把县里的内部摸排底册交上来。最宽口径约一万一千二百人，但这不是已经核定的失业人数，也不能把全部安置责任留给县里。",
            disposition="tentative_accept",
            used_belief_ids=["county_real_jobs"],
            commitment_summary="北山县提交内部就业底册，市里按核实结果推进培训和项目程序。",
            requires_formal_decision=True,
            consequence_note="高维民首次说出县内最宽就业口径，并要求市级安置支持与之绑定。",
        )
    return ParsedConversation(
        reply="这个条件我可以继续谈，但需要把双方先做什么、何时做到说清楚。涉及资金、项目或正式政策的部分，还要进入相应程序，不能只凭这次口头谈话。",
        disposition="tentative_accept",
        used_belief_ids=[],
        commitment_summary="与{}形成待确认的条件交换：{}".format(actor["name"], _shorten(message, 90)),
        requires_formal_decision=True,
        consequence_note="双方形成试探性条件交换，尚未取得正式效力。",
    )


def apply_conversation(
    game: StoredGame,
    actor_id: str,
    channel: str,
    intent: str,
    message: str,
    result: ParsedConversation,
) -> StoredGame:
    if game.status != "active":
        raise ValueError("本局已经结束")
    turn = turn_definition(game.turn_index, game.state)
    if actor_id not in turn["actor_ids"]:
        raise ValueError("这名人物与当前议题没有直接关系")

    updated = game.model_copy(deep=True)
    _ensure_interaction_state(updated.state)
    if int(updated.state["attention_remaining"]) <= 0:
        raise ValueError("本回合的会谈时段已经用完")

    allowed_beliefs = set(actor_belief_ids(actor_id))
    if not set(result.used_belief_ids).issubset(allowed_beliefs):
        raise ValueError("人物回答引用了其不应知道的信息")

    conversation_id = "{}-{}".format(
        game.turn_index + 1,
        len(updated.state["conversations"]) + 1,
    )
    entry = {
        "id": conversation_id,
        "turn": game.turn_index + 1,
        "actor_id": actor_id,
        "channel": channel,
        "intent": intent,
        "player_message": message.strip(),
        "reply": result.reply,
        "disposition": result.disposition,
        "consequence_note": result.consequence_note,
        "commitment_summary": result.commitment_summary,
        "requires_formal_decision": result.requires_formal_decision,
    }
    updated.state["conversations"].append(entry)
    updated.state["attention_remaining"] -= 1
    for belief_id in result.used_belief_ids:
        if belief_id not in updated.state["revealed_beliefs"]:
            updated.state["revealed_beliefs"].append(belief_id)

    if result.commitment_summary:
        updated.state["private_records"].append(
            {
                "id": "private-{}".format(conversation_id),
                "turn": game.turn_index + 1,
                "actor_id": actor_id,
                "kind": intent,
                "summary": result.commitment_summary,
                "status": "待正式化" if result.requires_formal_decision else "进行中",
                "visibility": "书面留痕" if channel == "written_inquiry" else "一对一知情",
                "requires_formal_decision": result.requires_formal_decision,
            }
        )

    relation_delta = 0
    if result.disposition in {"accept", "tentative_accept"}:
        relation_delta = 1
    elif result.disposition == "decline":
        relation_delta = -1
    updated.state["relations"][actor_id] = _clamp(
        int(updated.state["relations"][actor_id]) + relation_delta
    )
    updated.version += 1
    return updated


def apply_action(game: StoredGame, action: ParsedAction, choice: str) -> StoredGame:
    turn_index = game.turn_index
    if game.status != "active":
        raise ValueError("本局已经结束")
    if action.strategy_tag not in allowed_tags(turn_index):
        raise ValueError("行动不属于当前回合允许的策略")

    updated = game.model_copy(deep=True)
    state = updated.state
    _ensure_interaction_state(state)
    effect = EFFECTS[turn_index][action.strategy_tag]
    effect_lines: List[str] = []

    for metric_id, delta in effect.get("metrics", {}).items():
        before = int(state["metrics"][metric_id])
        after = _clamp(before + int(delta))
        state["metrics"][metric_id] = after
        label = _metric_label(metric_id)
        effect_lines.append("{} {}{}".format(label, "+" if delta > 0 else "", delta))

    for actor_id, delta in effect.get("relations", {}).items():
        before = int(state["relations"][actor_id])
        state["relations"][actor_id] = _clamp(before + int(delta))

    for flag in effect.get("flags", []):
        if flag not in state["flags"]:
            state["flags"].append(flag)

    commitment = effect.get("commitment")
    if commitment and commitment not in state["commitments"]:
        state["commitments"].append(commitment)
        effect_lines.append("形成后续承诺")

    responsibility = responsibility_for_tag(action.strategy_tag)
    formalized_records = 0
    lead_actor_id = responsibility.get("lead_actor_id")
    for record in state["private_records"]:
        if (
            record.get("requires_formal_decision")
            and lead_actor_id
            and record.get("actor_id") == lead_actor_id
        ):
            record["status"] = "已纳入正式决定"
            formalized_records += 1
    if formalized_records:
        effect_lines.append("{} 项私下酝酿已纳入正式责任链".format(formalized_records))

    if turn_index == 3:
        state["shock"] = choose_shock(updated)

    turn = turn_definition(turn_index, game.state)
    updated.history.append(
        {
            "turn": turn_index + 1,
            "title": turn["title"],
            "choice": choice,
            "directive_summary": action.directive_summary,
            "narrative": action.narrative,
            "effects": effect_lines,
            "npc_reactions": action.npc_reactions,
            "responsibility": responsibility,
        }
    )

    updated.turn_index += 1
    updated.version += 1
    state["attention_remaining"] = 3
    if updated.turn_index >= 6:
        updated.status = "completed"
        updated.outcome = build_outcome(updated)
    return updated


def choose_shock(game: StoredGame) -> str:
    flags = set(game.state.get("flags", []))
    candidates: List[str] = []
    if "merge_plan" in flags or "credit_signal" in flags or "implicit_support" in flags:
        candidates.extend(["credit_freeze", "credit_freeze"])
    if "true_jobs" not in flags:
        candidates.extend(["jobs_leak", "jobs_leak"])
    if "enterprise_window" in flags:
        candidates.extend(["orders_move", "orders_move"])
    if "unified_line" in flags or "hidden_dissent" in flags:
        candidates.extend(["signature_refusal", "signature_refusal"])
    candidates.extend(["credit_freeze", "jobs_leak", "orders_move", "signature_refusal"])
    rng = random.Random("{}:shock".format(game.seed))
    return rng.choice(candidates)


def build_outcome(game: StoredGame) -> Dict[str, Any]:
    metrics = game.state["metrics"]
    positive_ids = ["finance", "employment", "environment", "social", "org_credit", "team", "admin"]
    score = sum(metrics[item] for item in positive_ids) / len(positive_ids) - metrics["liability"] * 0.22

    if score >= 56:
        grade, title = "A", "在约束中建立了可持续的责任链"
    elif score >= 48:
        grade, title = "B", "阶段过关，但代价尚未结清"
    elif score >= 39:
        grade, title = "C", "勉强稳住局面，风险继续后移"
    else:
        grade, title = "D", "表面推进，系统性风险正在累积"

    achievements: List[str] = []
    risks: List[str] = []
    if metrics["environment"] >= 45:
        achievements.append("形成了可核验的阶段整改进度。")
    else:
        risks.append("环境整改进度仍不足，下一轮检查压力很高。")
    if metrics["finance"] >= 42:
        achievements.append("没有明显透支市级财政韧性。")
    else:
        risks.append("重组和支持安排正在挤压财政空间。")
    if metrics["employment"] >= 65:
        achievements.append("就业冲击总体处于可管理范围。")
    else:
        risks.append("停产和融资变化可能继续转化为欠薪与失业。")
    if metrics["team"] >= 52:
        achievements.append("市级班子形成了较清楚的共同责任。")
    else:
        risks.append("班子成员更倾向自保，后续执行仍依赖个人督办。")
    if metrics["liability"] <= 35:
        achievements.append("数据、程序和资金责任大体可追溯。")
    else:
        risks.append("会议口径、融资信号或数据差异留下了审计风险。")
    if game.state["commitments"]:
        risks.append("至少一项就业或政策支持承诺仍需在未来六个月兑现。")

    summary = (
        "十二周复核结束后，整改没有被简单判定为成功或失败。"
        "你的做法改变了岚州市获取真实信息、分配责任和处理坏消息的方式。"
    )
    epilogue = (
        "半年后，省里将再次核验首批整改和就业安置。"
        "本局结束，但今天形成的承诺、干部关系和责任记录仍会进入下一阶段。"
    )
    return {
        "grade": grade,
        "title": title,
        "summary": summary,
        "achievements": achievements or ["避免了局势在十二周内完全失控。"],
        "risks": risks or ["方案的长期效果仍需下一阶段验证。"],
        "epilogue": epilogue,
    }


def to_game_view(game: StoredGame) -> GameView:
    _ensure_interaction_state(game.state)
    metrics = [
        MetricView(
            id=metric_id,
            label=label,
            value=int(game.state["metrics"][metric_id]),
            description=description,
            higher_is_better=higher_is_better,
        )
        for metric_id, label, description, higher_is_better in METRIC_DEFINITIONS
    ]
    actors = [
        ActorView(
            id=actor_id,
            relation=int(game.state["relations"][actor_id]),
            name=actor["name"],
            title=actor["title"],
            public_position=actor["public_position"],
            known_note=actor["known_note"],
            work_style=actor["work_style"],
        )
        for actor_id, actor in ACTORS.items()
    ]
    turn_view = None
    if game.status == "active":
        raw = turn_definition(game.turn_index, game.state)
        turn_view = TurnView(
            number=game.turn_index + 1,
            phase=raw["phase"],
            title=raw["title"],
            date_label=raw["date_label"],
            briefing=raw["briefing"],
            dossier=DossierView(**raw["dossier"]),
            question=raw["question"],
            reports=[ReportView(**item) for item in raw["reports"]],
            actor_ids=raw["actor_ids"],
            options=[
                OptionView(
                    id=item["id"],
                    label=item["label"],
                    description=item["description"],
                    tradeoff=item["tradeoff"],
                    responsibility=ResponsibilityView(**responsibility_for_tag(item["id"])),
                )
                for item in raw["options"]
            ],
            custom_placeholder=raw["custom_placeholder"],
            attention_remaining=int(game.state["attention_remaining"]),
        )

    return GameView(
        id=game.id,
        version=game.version,
        player_name=game.player_name,
        mode=game.mode,
        model=game.model,
        api_base=game.api_base,
        status=game.status,
        turn=turn_view,
        metrics=metrics,
        actors=actors,
        history=[HistoryEntryView(**item) for item in game.history],
        commitments=list(game.state["commitments"]),
        conversations=[ConversationView(**item) for item in game.state["conversations"]],
        private_records=[PrivateRecordView(**item) for item in game.state["private_records"]],
        outcome=OutcomeView(**game.outcome) if game.outcome else None,
    )


def _ensure_interaction_state(state: Dict[str, Any]) -> None:
    state.setdefault("attention_remaining", 3)
    state.setdefault("conversations", [])
    state.setdefault("private_records", [])
    state.setdefault("revealed_beliefs", [])


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _metric_label(metric_id: str) -> str:
    for candidate, label, _, _ in METRIC_DEFINITIONS:
        if candidate == metric_id:
            return label
    return metric_id


def _shorten(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"
