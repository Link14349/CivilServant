from __future__ import annotations

import random
import uuid
from copy import deepcopy
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .daily_models import (
    ActionBudgetView,
    ActiveSceneView,
    ActivityView,
    AgentToolEffect,
    AgentUtterance,
    BriefingItemView,
    CalendarEntryView,
    DailyActorView,
    DailyGameView,
    DocumentView,
    GenerationView,
    IssueView,
    MetricView,
    NotificationView,
    PostSceneResult,
    ReferenceMaterialView,
    SceneParticipantView,
    SuperiorReaction,
    TranscriptTurnView,
)
from .daily_agent_tools import known_people_projection
from .daily_scenario import (
    ACTORS,
    ACTOR_DIRECTORY_GROUPS,
    INITIAL_DOCUMENTS,
    INITIAL_ISSUES,
    INITIAL_METRICS,
    LOCATIONS,
    MEETING_TYPES,
    METRIC_DEFINITIONS,
    PUBLIC_REFERENCE_MATERIALS,
    STANDING_COMMITTEE_MEMBER_IDS,
    TEMPLATE_UTTERANCES,
    actor_acquaintance_ids,
    actor_belief_ids,
    actor_context,
    actor_label,
)
from .models import StoredGame


SCHEMA_VERSION = 3
SUPPORTED_DAILY_SCHEMA_VERSIONS = {2, 3}
START_DATE = date(2026, 9, 1)
DAILY_ACTION_POINTS = 4
ACTION_COSTS = {
    "conversation": 1,
    "meeting": 2,
    "field_visit": 2,
    "superior_meeting": 2,
}


def _initial_actor_runtime(actor_id: str, current_date: str = START_DATE.isoformat()) -> Dict[str, Any]:
    return {
        "memories": [],
        "tasks": [],
        "workload": 0,
        "known_beliefs": actor_belief_ids(actor_id),
        "knowledge": [
            {
                "id": item["id"],
                "claim": item["content"],
                "source": item["source"],
                "acquired_date": current_date,
                "confidence": "high",
                "kind": "initial_private",
                "status": "active",
                "related_actor_ids": [],
                "related_issue_ids": [],
            }
            for item in ACTORS[actor_id]["beliefs"]
        ],
        "relationships": {
            target_id: {
                "score": 50,
                "last_updated": current_date,
                "note": "只有公开工作关系，尚无足够亲历判断。",
            }
            for target_id in actor_acquaintance_ids(actor_id)
        },
    }


def create_daily_game(
    player_name: str,
    background: str,
    mode: str,
    model: str,
    api_base: str,
    seed: Optional[int] = None,
) -> StoredGame:
    game_seed = seed or random.SystemRandom().randint(1, 2_147_483_647)
    start = START_DATE
    state: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "background": background,
        "current_date": start.isoformat(),
        "day_number": 1,
        "day_phase": "reviewing",
        "action_total": DAILY_ACTION_POINTS,
        "action_remaining": DAILY_ACTION_POINTS,
        "id_counter": 100,
        "metrics": deepcopy(INITIAL_METRICS),
        "relations": {actor_id: 50 for actor_id in ACTORS},
        "player_beliefs": [],
        "actor_runtime": {
            actor_id: _initial_actor_runtime(actor_id, start.isoformat())
            for actor_id in ACTORS
        },
        "commitments": [],
        "scene_archive": [],
        "issues": deepcopy(INITIAL_ISSUES),
        "documents": [],
        "document_tasks": [],
        "calendar": [],
        "briefing": [],
        "notifications": [],
        "activity": [],
        "active_scene": None,
        "delayed_triggers": [],
        "event_history": [],
        "processed_keys": {},
        "flags": [],
    }
    state["issues"][0]["deadline"] = (start + timedelta(days=5)).isoformat()
    for template in INITIAL_DOCUMENTS:
        document = deepcopy(template)
        document.update(
            {
                "version": 1,
                "created_date": start.isoformat(),
                "due_date": (
                    (start + timedelta(days=5)).isoformat()
                    if document["id"] == "doc-superior-notice"
                    else None
                ),
                "annotations": [],
            }
        )
        state["documents"].append(document)

    standing_date = (start + timedelta(days=2)).isoformat()
    state["calendar"].append(
        {
            "id": _new_id(state, "cal"),
            "date": standing_date,
            "kind": "meeting",
            "title": "例行市委常委会",
            "participant_ids": [item for item in STANDING_COMMITTEE_MEMBER_IDS if item != "player"],
            "location_id": None,
            "meeting_type": "standing_committee",
            "discussion_mode": "chaired",
            "action_cost": 2,
            "mandatory": False,
            "status": "scheduled",
            "source": "市委办公室例行安排",
            "notified": True,
        }
    )
    state["briefing"] = _assemble_briefing(state)
    game = StoredGame(
        id=str(uuid.uuid4()),
        version=1,
        player_name=player_name.strip(),
        mode=mode,
        model=model,
        api_base=api_base.rstrip("/"),
        seed=game_seed,
        turn_index=0,
        status="active",
        state=state,
        history=[],
        outcome=None,
    )
    return game


def is_daily_game(game: StoredGame) -> bool:
    return int(game.state.get("schema_version", 0)) in SUPPORTED_DAILY_SCHEMA_VERSIONS


def hydrate_daily_actor_state(game: StoredGame) -> StoredGame:
    """Add newly shipped Agent state to an existing snapshot without changing its version."""
    _require_daily(game)
    relations = game.state.get("relations", {})
    runtime = game.state.get("actor_runtime", {})
    needs_hydration = (
        int(game.state.get("schema_version", 0)) != SCHEMA_VERSION
        or "commitments" not in game.state
        or "scene_archive" not in game.state
        or any(
            actor_id not in relations
            or actor_id not in runtime
            or "knowledge" not in runtime.get(actor_id, {})
            or "tasks" not in runtime.get(actor_id, {})
            or "memories" not in runtime.get(actor_id, {})
            or "relationships" not in runtime.get(actor_id, {})
            for actor_id in ACTORS
        )
    )
    if not needs_hydration:
        return game
    updated = game.model_copy(deep=True)
    updated.state["schema_version"] = SCHEMA_VERSION
    updated.state.setdefault("commitments", [])
    updated.state.setdefault("scene_archive", [])
    updated_relations = updated.state.setdefault("relations", {})
    updated_runtime = updated.state.setdefault("actor_runtime", {})
    for actor_id in ACTORS:
        updated_relations.setdefault(actor_id, 50)
        actor_runtime = updated_runtime.setdefault(
            actor_id,
            _initial_actor_runtime(actor_id, updated.state["current_date"]),
        )
        defaults = _initial_actor_runtime(actor_id, updated.state["current_date"])
        actor_runtime.setdefault("memories", [])
        actor_runtime.setdefault("tasks", [])
        actor_runtime.setdefault("workload", 0)
        actor_runtime.setdefault("known_beliefs", defaults["known_beliefs"])
        actor_runtime.setdefault("knowledge", defaults["knowledge"])
        relationships = actor_runtime.setdefault("relationships", {})
        for target_id, relationship in defaults["relationships"].items():
            relationships.setdefault(target_id, relationship)
    for document in updated.state.get("documents", []):
        document.setdefault("handled_date", None)
    return updated


def command_was_processed(game: StoredGame, key: str) -> bool:
    return key in game.state.get("processed_keys", {})


def schedule_calendar_entry(
    game: StoredGame,
    *,
    idempotency_key: str,
    target_date: str,
    kind: str,
    title: str,
    participant_ids: Sequence[str],
    location_id: Optional[str],
    meeting_type: Optional[str],
    discussion_mode: Optional[str],
    notified: bool,
) -> StoredGame:
    _require_daily_active(game)
    if target_date < game.state["current_date"]:
        raise ValueError("不能把日程安排到过去")
    if kind == "meeting":
        if meeting_type not in MEETING_TYPES:
            raise ValueError("未知的会议类型")
        cost = int(MEETING_TYPES[meeting_type]["cost"])
    else:
        cost = ACTION_COSTS[kind]
    _validate_actor_ids(participant_ids)
    if location_id and location_id not in LOCATIONS:
        raise ValueError("未知的调研地点")

    reserved = sum(
        int(item["action_cost"])
        for item in game.state["calendar"]
        if item["date"] == target_date and item["status"] not in {"canceled", "completed"}
    )
    if reserved + cost > DAILY_ACTION_POINTS:
        raise ValueError("这一天的确定日程已经超过行动点预算")

    updated = game.model_copy(deep=True)
    updated.state["calendar"].append(
        {
            "id": _new_id(updated.state, "cal"),
            "date": target_date,
            "kind": kind,
            "title": title.strip(),
            "participant_ids": list(dict.fromkeys(participant_ids)),
            "location_id": location_id,
            "meeting_type": meeting_type,
            "discussion_mode": discussion_mode,
            "action_cost": cost,
            "mandatory": False,
            "status": "due" if target_date == updated.state["current_date"] else "scheduled",
            "source": "玩家预定",
            "notified": notified,
        }
    )
    _add_activity(updated.state, "schedule", "安排未来日程", "{}：{}".format(target_date, title))
    return _finish_command(updated, idempotency_key)


def cancel_calendar_entry(
    game: StoredGame,
    *,
    idempotency_key: str,
    entry_id: str,
    reason: str,
) -> StoredGame:
    _require_daily_active(game)
    updated = game.model_copy(deep=True)
    entry = _find_by_id(updated.state["calendar"], entry_id)
    if entry["status"] in {"completed", "canceled"}:
        raise ValueError("这项日程已经结束")
    if entry["mandatory"]:
        raise ValueError("强制日程需要明确拒绝或由上级改期，不能直接取消")
    entry["status"] = "canceled"
    _add_activity(updated.state, "schedule", "取消日程", "{}；原因：{}".format(entry["title"], reason))
    if entry["date"] == updated.state["current_date"]:
        _change_metric(updated.state, "org_credit", -1)
    return _finish_command(updated, idempotency_key)


def start_conversation(
    game: StoredGame,
    *,
    idempotency_key: str,
    actor_id: str,
    channel: str,
    opening: Optional[str] = None,
    superior: bool = False,
    calendar_entry_id: Optional[str] = None,
) -> StoredGame:
    _require_can_start_scene(game)
    if actor_id not in ACTORS:
        raise ValueError("没有找到这名人物")
    kind = "superior_meeting" if superior or actor_id == "superior" else "conversation"
    cost = ACTION_COSTS[kind]
    updated = game.model_copy(deep=True)
    _spend_action_points(updated.state, cost)
    scene = _base_scene(
        updated.state,
        kind=kind,
        title="与{}面谈".format(ACTORS[actor_id]["name"]),
        action_cost=cost,
        calendar_entry_id=calendar_entry_id,
    )
    scene["channel"] = channel
    scene["participants"] = [
        _participant("player", "chair"),
        _participant(actor_id, "counterpart"),
    ]
    if opening and opening.strip():
        _append_transcript(scene, "player", updated.player_name, "player", opening.strip())
    updated.state["active_scene"] = scene
    updated.state["day_phase"] = "scene_active"
    _mark_calendar_active(updated.state, calendar_entry_id)
    _add_activity(updated.state, "conversation", scene["title"], "面谈已经开始。")
    return _finish_command(updated, idempotency_key)


def start_meeting(
    game: StoredGame,
    *,
    idempotency_key: str,
    meeting_type: str,
    discussion_mode: str,
    title: str,
    agenda: str,
    participant_ids: Sequence[str],
    calendar_entry_id: Optional[str] = None,
) -> StoredGame:
    _require_can_start_scene(game)
    if meeting_type not in MEETING_TYPES:
        raise ValueError("未知的会议类型")
    if discussion_mode not in {"free", "chaired"}:
        raise ValueError("未知的讨论方式")
    unique_participants = list(dict.fromkeys(participant_ids))
    _validate_actor_ids(unique_participants)
    if not unique_participants:
        raise ValueError("会议至少需要一名 NPC 参加")
    cost = int(MEETING_TYPES[meeting_type]["cost"])
    updated = game.model_copy(deep=True)
    _spend_action_points(updated.state, cost)
    scene = _base_scene(
        updated.state,
        kind="meeting",
        title=title.strip(),
        action_cost=cost,
        calendar_entry_id=calendar_entry_id,
    )
    scene.update(
        {
            "meeting_type": meeting_type,
            "discussion_mode": discussion_mode,
            "agenda": agenda.strip(),
            "participants": [_participant("player", "chair")]
            + [
                _participant(
                    actor_id,
                    "member"
                    if actor_id in STANDING_COMMITTEE_MEMBER_IDS
                    else "invitee",
                    can_vote=actor_id in STANDING_COMMITTEE_MEMBER_IDS,
                )
                for actor_id in unique_participants
            ],
            "can_vote": meeting_type == "standing_committee"
            and _standing_committee_present_count(unique_participants) >= 6,
        }
    )
    _append_transcript(
        scene,
        "system",
        "会议记录",
        "system",
        "会议开始。议题：{}{}{}".format(
            agenda.strip(),
            "" if agenda.strip().endswith(("。", "！", "？", "；")) else "。",
            MEETING_TYPES[meeting_type]["formal_effect"],
        ),
    )
    updated.state["active_scene"] = scene
    updated.state["day_phase"] = "scene_active"
    _mark_calendar_active(updated.state, calendar_entry_id)
    _add_activity(updated.state, "meeting", scene["title"], "会议开始，采用{}。".format("自由磋商" if discussion_mode == "free" else "玩家主持"))
    return _finish_command(updated, idempotency_key)


def start_field_visit(
    game: StoredGame,
    *,
    idempotency_key: str,
    location_id: str,
    notified: bool,
    calendar_entry_id: Optional[str] = None,
) -> StoredGame:
    _require_can_start_scene(game)
    if location_id not in LOCATIONS:
        raise ValueError("未知的调研地点")
    updated = game.model_copy(deep=True)
    cost = ACTION_COSTS["field_visit"]
    _spend_action_points(updated.state, cost)
    location = LOCATIONS[location_id]
    observation = _field_observation(updated, location_id, notified)
    scene = _base_scene(
        updated.state,
        kind="field_visit",
        title="调研：{}".format(location["label"]),
        action_cost=cost,
        calendar_entry_id=calendar_entry_id,
    )
    scene.update(
        {
            "location_id": location_id,
            "notified": notified,
            "participants": [_participant("player", "chair")],
        }
    )
    _append_transcript(scene, "system", "现场观察", "system", observation)
    for belief_id in location["reveals"]:
        if belief_id not in updated.state["player_beliefs"]:
            updated.state["player_beliefs"].append(belief_id)
    updated.state["active_scene"] = scene
    updated.state["day_phase"] = "scene_active"
    _mark_calendar_active(updated.state, calendar_entry_id)
    _add_activity(updated.state, "field_visit", scene["title"], observation)
    return _finish_command(updated, idempotency_key)


def add_player_speech(
    game: StoredGame,
    *,
    idempotency_key: str,
    record_version: int,
    text: str,
) -> StoredGame:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    if int(scene["record_version"]) != record_version:
        raise ValueError("场景记录已经更新，请刷新后重试")
    updated = game.model_copy(deep=True)
    scene = updated.state["active_scene"]
    if scene["generation"]["status"] == "thinking":
        scene["generation"]["status"] = "canceled"
        scene["generation"]["message"] = "玩家发言使本次生成失效。"
    _append_transcript(scene, "player", updated.player_name, "player", text.strip())
    _add_activity(updated.state, "speech", "玩家发言", _shorten(text.strip(), 120))
    return _finish_command(updated, idempotency_key)


def add_conversation_reply(
    game: StoredGame,
    *,
    utterance: AgentUtterance,
) -> StoredGame:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    if scene["kind"] not in {"conversation", "superior_meeting"}:
        raise ValueError("当前不是个别面谈")
    actor_id = next(
        item["actor_id"]
        for item in scene["participants"]
        if item["actor_id"] != "player"
    )
    _validate_used_beliefs(game, actor_id, utterance.used_belief_ids)
    updated = game.model_copy(deep=True)
    _append_transcript(
        updated.state["active_scene"],
        actor_id,
        ACTORS[actor_id]["name"],
        "npc",
        utterance.text,
    )
    for belief_id in utterance.used_belief_ids:
        if belief_id not in {item["id"] for item in PUBLIC_REFERENCE_MATERIALS} and belief_id not in updated.state["player_beliefs"]:
            updated.state["player_beliefs"].append(belief_id)
    _apply_agent_tool_effects(
        updated.state,
        updated.state["active_scene"],
        actor_id,
        utterance.tool_effects,
        settlement=False,
    )
    updated.version += 1
    return updated


def begin_meeting_generation(
    game: StoredGame,
    *,
    idempotency_key: str,
    record_version: int,
    nominated_actor_id: Optional[str] = None,
    willing_actor_ids: Optional[Sequence[str]] = None,
) -> Tuple[StoredGame, Optional[str]]:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    if scene["kind"] != "meeting":
        raise ValueError("当前不是会议场景")
    if int(scene["record_version"]) != record_version:
        raise ValueError("会议记录已经更新，请刷新后重试")
    if scene["generation"]["status"] == "thinking":
        raise ValueError("已经有人正在形成发言")

    participant_ids = [
        item["actor_id"] for item in scene["participants"] if item["actor_id"] != "player"
    ]
    if scene["discussion_mode"] == "chaired":
        if not nominated_actor_id or nominated_actor_id not in participant_ids:
            raise ValueError("主持模式需要点名一名参会者")
        selected = nominated_actor_id
    else:
        if willing_actor_ids is None:
            selected = _choose_free_speaker(game, scene, participant_ids)
        else:
            willing = [item for item in willing_actor_ids if item in participant_ids]
            selected = (
                _rng(game, "speaker-choice:{}:{}".format(scene["id"], scene["record_version"])).choice(willing)
                if willing
                else None
            )

    updated = game.model_copy(deep=True)
    updated_scene = updated.state["active_scene"]
    if selected is None:
        updated_scene["silence_count"] += 1
        _append_transcript(
            updated_scene,
            "system",
            "会议记录",
            "system",
            "短暂沉默。当前没有参会者主动要求发言，主持人可以点名或亲自发言。",
        )
        return _finish_command(updated, idempotency_key), None

    generation_id = _new_id(updated.state, "gen")
    updated_scene["generation"] = {
        "id": generation_id,
        "status": "thinking",
        "actor_id": selected,
        "message": "{}正在形成发言，可由玩家发言打断。".format(ACTORS[selected]["name"]),
        "started_record_version": updated_scene["record_version"],
    }
    return _finish_command(updated, idempotency_key), selected


def commit_meeting_speech(
    game: StoredGame,
    *,
    generation_id: str,
    actor_id: str,
    utterance: AgentUtterance,
) -> StoredGame:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    generation = scene["generation"]
    if (
        generation.get("id") != generation_id
        or generation.get("status") != "thinking"
        or generation.get("actor_id") != actor_id
        or int(generation.get("started_record_version", -1)) != int(scene["record_version"])
    ):
        raise ValueError("这次发言生成已经失效")
    _validate_used_beliefs(game, actor_id, utterance.used_belief_ids)
    updated = game.model_copy(deep=True)
    updated_scene = updated.state["active_scene"]
    _append_transcript(
        updated_scene,
        actor_id,
        ACTORS[actor_id]["name"],
        "npc",
        utterance.text,
    )
    _apply_agent_tool_effects(
        updated.state,
        updated_scene,
        actor_id,
        utterance.tool_effects,
        settlement=False,
    )
    updated_scene["generation"] = {
        "id": generation_id,
        "status": "completed",
        "actor_id": actor_id,
        "message": "发言已经写入会议记录。",
    }
    updated.version += 1
    return updated


def discard_generation(game: StoredGame, generation_id: str, message: str) -> StoredGame:
    if not game.state.get("active_scene"):
        return game
    generation = game.state["active_scene"].get("generation", {})
    if generation.get("id") != generation_id or generation.get("status") != "thinking":
        return game
    updated = game.model_copy(deep=True)
    updated.state["active_scene"]["generation"]["status"] = "discarded"
    updated.state["active_scene"]["generation"]["message"] = message
    updated.version += 1
    return updated


def vote_in_meeting(
    game: StoredGame,
    *,
    idempotency_key: str,
    record_version: int,
    resolution: str,
) -> StoredGame:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    if scene["kind"] != "meeting" or scene.get("meeting_type") != "standing_committee":
        raise ValueError("只有市委常委会可以进行本项表决")
    if int(scene["record_version"]) != record_version:
        raise ValueError("会议记录已经更新")
    participants = [
        item["actor_id"]
        for item in scene["participants"]
        if item.get("can_vote") and item["actor_id"] != "player"
    ]
    if _standing_committee_present_count(participants) < 6:
        raise ValueError("到会常委不足半数，不能表决")
    if scene.get("vote_result"):
        raise ValueError("本议题已经表决")

    updated = game.model_copy(deep=True)
    yes_votes = 1
    vote_lines = ["市委书记：赞成"]
    for actor_id in participants:
        relation = int(updated.state["relations"][actor_id])
        rng = _rng(updated, "vote:{}:{}:{}".format(updated.state["day_number"], scene["id"], actor_id))
        yes = rng.random() < (0.46 + max(-0.12, min(0.18, (relation - 50) / 100)))
        yes_votes += int(yes)
        vote_lines.append("{}：{}".format(ACTORS[actor_id]["name"], "赞成" if yes else "保留/反对"))
    passed = yes_votes >= 6
    result = "{}（赞成 {} 票；按十一名应到常委计算，至少六票通过）".format(
        "通过" if passed else "未通过",
        yes_votes,
    )
    updated_scene = updated.state["active_scene"]
    updated_scene["vote_result"] = result
    _append_transcript(
        updated_scene,
        "system",
        "表决记录",
        "system",
        "决议：{}\n{}\n{}".format(resolution.strip(), "；".join(vote_lines), result),
    )
    if passed:
        _change_metric(updated.state, "team", 2)
        _add_activity(
            updated.state,
            "decision",
            "常委会形成决定",
            "{}。该决定只在党委权限范围内生效，具体行政事项仍需后续程序。".format(resolution.strip()),
        )
    return _finish_command(updated, idempotency_key)


def close_scene(
    game: StoredGame,
    *,
    idempotency_key: str,
    record_version: int,
    resolution: Optional[str] = None,
    post_scene_results: Optional[Mapping[str, PostSceneResult]] = None,
) -> StoredGame:
    _require_active_scene(game)
    scene = game.state["active_scene"]
    if int(scene["record_version"]) != record_version:
        raise ValueError("场景记录已经更新，请刷新后重试")
    if scene["generation"]["status"] == "thinking":
        raise ValueError("仍有发言正在生成，请先打断或等待")

    updated = game.model_copy(deep=True)
    scene = updated.state["active_scene"]
    transcript_text = "\n".join(item["text"] for item in scene["transcript"])
    _settle_scene(updated, scene, transcript_text, resolution, post_scene_results)
    calendar_entry_id = scene.get("calendar_entry_id")
    if calendar_entry_id:
        entry = _find_by_id(updated.state["calendar"], calendar_entry_id)
        entry["status"] = "completed"
    _add_activity(
        updated.state,
        "scene_closed",
        "{}结束".format(scene["title"]),
        resolution.strip() if resolution else "场景记录已经冻结，人物开始处理会后事项。",
    )
    archived_scene = deepcopy(scene)
    archived_scene["closed_date"] = updated.state["current_date"]
    archived_scene["resolution"] = resolution.strip() if resolution else None
    archived_scene["status"] = "completed"
    updated.state["scene_archive"].append(archived_scene)
    updated.state["active_scene"] = None
    updated.state["day_phase"] = "action"
    _activate_next_due_schedule(updated)
    return _finish_command(updated, idempotency_key)


def act_on_document(
    game: StoredGame,
    *,
    idempotency_key: str,
    document_id: str,
    operation: str,
    note: str,
    recipient_id: Optional[str],
) -> StoredGame:
    _require_daily_active(game)
    updated = game.model_copy(deep=True)
    document = _find_by_id(updated.state["documents"], document_id)
    if document["status"] == "archived":
        raise ValueError("归档文件不能继续处理")
    if operation == "annotate":
        if not note.strip():
            raise ValueError("批示不能为空")
        document["annotations"].append(note.strip())
        document["version"] += 1
        document["handled_date"] = updated.state["current_date"]
        _add_activity(updated.state, "document", "批示文件", "{}：{}".format(document["title"], note.strip()))
    elif operation == "return":
        document["status"] = "returned"
        document["annotations"].append(note.strip() or "请补充事实、依据和待拍板事项后重报。")
        document["version"] += 1
        document["handled_date"] = updated.state["current_date"]
        _add_activity(updated.state, "document", "退回文件", document["title"])
    elif operation == "forward":
        if not recipient_id:
            raise ValueError("转交文件需要指定收件人")
        if recipient_id not in ACTORS:
            raise ValueError("未知的收件人")
        document["recipient_ids"] = list(dict.fromkeys(document["recipient_ids"] + [recipient_id]))
        document["status"] = "submitted"
        document["version"] += 1
        document["handled_date"] = updated.state["current_date"]
        _add_activity(
            updated.state,
            "document",
            "转交文件",
            "{}转交给{}。".format(document["title"], ACTORS[recipient_id]["name"]),
        )
    elif operation == "archive":
        document["status"] = "archived"
        document["version"] += 1
        document["handled_date"] = updated.state["current_date"]
    else:
        raise ValueError("不支持的文件操作")
    return _finish_command(updated, idempotency_key)


def create_document_task(
    game: StoredGame,
    *,
    idempotency_key: str,
    author_id: str,
    title: str,
    document_type: str,
    instructions: str,
    source_document_ids: Sequence[str],
) -> StoredGame:
    _require_daily_active(game)
    if author_id not in ACTORS:
        raise ValueError("没有找到起草人")
    for document_id in source_document_ids:
        _find_by_id(game.state["documents"], document_id)
    updated = game.model_copy(deep=True)
    due = (_parse_date(updated.state["current_date"]) + timedelta(days=1)).isoformat()
    updated.state["document_tasks"].append(
        {
            "id": _new_id(updated.state, "task"),
            "author_id": author_id,
            "title": title.strip(),
            "document_type": document_type,
            "instructions": instructions.strip(),
            "source_document_ids": list(source_document_ids),
            "created_date": updated.state["current_date"],
            "due_date": due,
            "status": "queued",
        }
    )
    updated.state["actor_runtime"][author_id]["workload"] += 1
    _add_activity(
        updated.state,
        "document_task",
        "交办起草",
        "{}将在{}前起草《{}》。".format(ACTORS[author_id]["name"], due, title.strip()),
    )
    return _finish_command(updated, idempotency_key)


def submit_document(
    game: StoredGame,
    *,
    idempotency_key: str,
    document_id: str,
    recipient_id: str,
    cover_note: str,
    superior_reaction: Optional[SuperiorReaction] = None,
) -> StoredGame:
    _require_daily_active(game)
    if recipient_id not in ACTORS:
        raise ValueError("未知的收件人")
    updated = game.model_copy(deep=True)
    document = _find_by_id(updated.state["documents"], document_id)
    if document["status"] not in {"draft", "ready", "received", "returned"}:
        raise ValueError("当前文件状态不能提交")
    document["status"] = "submitted"
    document["recipient_ids"] = list(dict.fromkeys(document["recipient_ids"] + [recipient_id]))
    document["version"] += 1
    document["handled_date"] = updated.state["current_date"]
    if cover_note.strip():
        document["annotations"].append("呈报说明：{}".format(cover_note.strip()))
    _add_activity(
        updated.state,
        "submission",
        "提交文件",
        "《{}》已报送{}，原始作者和版本沿革保持不变。".format(
            document["title"],
            ACTORS[recipient_id]["name"],
        ),
    )
    if recipient_id == "superior":
        if superior_reaction is None:
            rng = _rng(updated, "superior-reaction:{}:{}".format(document_id, document["version"]))
            delay = rng.randint(1, 3)
            expires_after = 14
            detail = None
            condition = None
        else:
            delay = superior_reaction.delay_days or 1
            expires_after = superior_reaction.expires_after_days or 14
            detail = superior_reaction.proposed_action
            condition = superior_reaction.condition
        if superior_reaction is None or superior_reaction.reaction_kind in {"conditional_follow_up", "delayed"}:
            updated.state["delayed_triggers"].append(
                {
                    "id": _new_id(updated.state, "trigger"),
                    "kind": "superior_document_reaction",
                    "source_id": document_id,
                    "due_date": (_parse_date(updated.state["current_date"]) + timedelta(days=delay)).isoformat(),
                    "expires_date": (_parse_date(updated.state["current_date"]) + timedelta(days=expires_after)).isoformat(),
                    "status": "scheduled",
                    "detail": detail,
                    "condition": condition,
                }
            )
        _add_notification(
            updated.state,
            "上级已收件",
            superior_reaction.immediate_reply
            if superior_reaction is not None
            else "省委办公厅确认收到《{}》，是否进一步反馈尚未确定。".format(document["title"]),
            "neutral",
        )
    return _finish_command(updated, idempotency_key)


def close_day(game: StoredGame, *, idempotency_key: str) -> StoredGame:
    _require_daily_active(game)
    if game.state.get("active_scene"):
        raise ValueError("请先结束当前互动场景")
    mandatory_due = [
        item
        for item in game.state["calendar"]
        if item["date"] == game.state["current_date"]
        and item["mandatory"]
        and item["status"] not in {"completed", "canceled"}
    ]
    if mandatory_due:
        raise ValueError("仍有必须处理的当日日程")

    updated = game.model_copy(deep=True)
    current = _parse_date(updated.state["current_date"])
    for entry in updated.state["calendar"]:
        if entry["date"] == current.isoformat() and entry["status"] in {"scheduled", "due"}:
            entry["status"] = "conflict"
            _change_metric(updated.state, "org_credit", -1)
    _archive_handled_documents(updated.state, current.isoformat())
    _settle_daily_world(updated)
    next_date = current + timedelta(days=1)
    updated.state["current_date"] = next_date.isoformat()
    updated.state["day_number"] += 1
    updated.turn_index = updated.state["day_number"] - 1
    updated.state["day_phase"] = "reviewing"
    updated.state["action_total"] = DAILY_ACTION_POINTS
    updated.state["action_remaining"] = DAILY_ACTION_POINTS
    _complete_due_document_tasks(updated)
    _resolve_delayed_triggers(updated)
    _generate_dynamic_event(updated)
    for entry in updated.state["calendar"]:
        if entry["date"] == next_date.isoformat() and entry["status"] == "scheduled":
            entry["status"] = "due"
    updated.state["briefing"] = _assemble_briefing(updated.state)
    _activate_next_due_schedule(updated)
    _add_activity(updated.state, "day", "进入新的一天", "第{}日，{}。".format(updated.state["day_number"], next_date.isoformat()))
    return _finish_command(updated, idempotency_key)


def _archive_handled_documents(state: Dict[str, Any], closing_date: str) -> None:
    for document in state["documents"]:
        if document.get("handled_date") != closing_date or document["status"] == "archived":
            continue
        document["status"] = "archived"
        _add_activity(
            state,
            "archive",
            "文件转入归档",
            "《{}》已在当日处理完毕，次日起不再占用待阅文件列表。".format(document["title"]),
        )


def template_conversation_utterance(game: StoredGame, actor_id: str, message: str) -> AgentUtterance:
    context = actor_context(actor_id)
    text = message.strip()
    used: List[str] = []
    reply = TEMPLATE_UTTERANCES[actor_id]
    keyword_map = {
        "mayor": [("资金", "mayor_budget_gap"), ("工资", "mayor_cash_crisis"), ("现金", "mayor_cash_crisis")],
        "secretary_general": [("就业", "secretary_jobs_revision"), ("前任", "secretary_old_minutes"), ("纪要", "secretary_old_minutes")],
        "county_secretary": [("就业", "county_real_jobs"), ("名单", "county_real_jobs"), ("补贴", "county_subsidy_arrears")],
        "nanchuan_secretary": [("验收", "nanchuan_acceptance_gap"), ("冲刷", "nanchuan_acceptance_gap"), ("物资", "nanchuan_material_shortage")],
        "linjiang_secretary": [("土壤", "linjiang_brownfield_cost"), ("治理成本", "linjiang_brownfield_cost")],
        "dongning_secretary": [("加工园", "dongning_processing_gap"), ("冷链", "dongning_processing_gap")],
        "qingyuan_secretary": [("公路", "qingyuan_road_risk"), ("边坡", "qingyuan_road_risk")],
        "hezhou_secretary": [("学校", "hezhou_school_transport"), ("校车", "hezhou_school_transport")],
        "finance_director": [("新增支出", "finance_competing_requests"), ("可统筹", "finance_competing_requests"), ("预算", "finance_competing_requests")],
        "development_reform_director": [("项目", "development_project_maturity"), ("要素", "development_project_maturity")],
        "industry_bureau_director": [("就业", "industry_employment_estimate"), ("工信", "industry_employment_estimate")],
        "human_resources_director": [("名单", "human_resources_roster_gap"), ("派遣", "human_resources_roster_gap")],
        "water_director": [("险段", "water_design_gap"), ("冲刷", "water_design_gap"), ("加固", "water_design_gap")],
        "emergency_director": [("物资", "emergency_stock_transfer"), ("调运", "emergency_stock_transfer")],
        "state_assets_director": [("国企", "state_assets_capacity"), ("融资空间", "state_assets_capacity")],
        "audit_director": [("审计", "audit_unsettled_funds"), ("专项资金", "audit_unsettled_funds")],
        "natural_resources_director": [("土地", "natural_resources_mortgage_overlap"), ("抵押", "natural_resources_mortgage_overlap")],
        "housing_director": [("排水", "housing_drainage_gap"), ("内涝", "housing_drainage_gap")],
        "transport_director": [("桥梁", "transport_corridor_overlap"), ("货运", "transport_corridor_overlap")],
        "agriculture_director": [("农田", "agriculture_flood_exposure"), ("排涝站", "agriculture_flood_exposure")],
        "health_director": [("医院", "health_hospital_arrears"), ("耗材", "health_hospital_arrears")],
        "education_director": [("学位", "education_capacity_gap"), ("小学", "education_capacity_gap")],
        "petitions_director": [("重复来访", "petitions_repeated_cases"), ("信访", "petitions_repeated_cases")],
        "public_security_director": [("讨薪", "public_security_contractors"), ("承包商", "public_security_contractors")],
        "environment_director": [("停产", "environment_window"), ("监测", "environment_window")],
        "chairman": [("抵押", "chairman_collateral_truth"), ("并购", "chairman_order_move")],
        "banker": [("授信", "bank_credit_line"), ("贷款", "bank_credit_line")],
        "superior": [("延期", "superior_prior_delay"), ("上报", "superior_prior_delay")],
    }
    for keyword, belief_id in keyword_map.get(actor_id, []):
        if keyword in text and belief_id not in used:
            used.append(belief_id)
    if used:
        belief_lookup = {item["id"]: item for item in context["beliefs"]}
        details = "；".join(belief_lookup[item]["content"] for item in used)
        reply = "{} 我能确认的内部情况是：{}。".format(reply, details)
    else:
        public_topic_map = [
            ("南川", "ref-nanchuan"),
            ("临江", "ref-linjiang"),
            ("北山", "ref-beishan"),
            ("东宁", "ref-dongning"),
            ("青源", "ref-qingyuan"),
            ("和州", "ref-hezhou"),
            ("人口", "ref-city-society"),
            ("就业结构", "ref-city-society"),
            ("经济", "ref-city-economy"),
            ("财政基本盘", "ref-city-economy"),
            ("自然", "ref-city-geography"),
            ("地形", "ref-city-geography"),
            ("气候", "ref-city-geography"),
            ("交通", "ref-city-infrastructure"),
            ("基础设施", "ref-city-infrastructure"),
        ]
        reference_by_id = {item["id"]: item for item in PUBLIC_REFERENCE_MATERIALS}
        public_id = next((reference_id for keyword, reference_id in public_topic_map if keyword in text), None)
        if public_id:
            used.append(public_id)
            reply = "{} 按公开市情资料，{}".format(reply, reference_by_id[public_id]["summary"])
    if not used and ("不知道" in text or "真实" in text):
        reply = "{} 这件事超出我目前能确认的范围，建议指定渠道核查，不宜让我替别人下结论。".format(reply)
    return AgentUtterance(text=reply, used_belief_ids=used)


def template_meeting_utterance(game: StoredGame, actor_id: str) -> AgentUtterance:
    scene = game.state["active_scene"]
    last_turn = scene["transcript"][-1]["text"] if scene["transcript"] else ""
    base = TEMPLATE_UTTERANCES[actor_id]
    if last_turn and actor_id == "secretary_general":
        base = "{} 我建议把刚才的分歧分别记为事实核查、方案起草和待正式决策事项。".format(base)
    return AgentUtterance(text=base, used_belief_ids=[])


def actor_agent_projection(game: StoredGame, actor_id: str) -> Dict[str, Any]:
    game = hydrate_daily_actor_state(game)
    context = actor_context(actor_id)
    context.pop("beliefs", None)
    state = game.state
    scene = state.get("active_scene")
    visible_document_ids = [
        document["id"]
        for document in state["documents"]
        if actor_id == document["author_id"] or actor_id in document["recipient_ids"]
    ]
    visible_documents = [
        {
            "id": document["id"],
            "version": document["version"],
            "title": document["title"],
            "document_type": document["document_type"],
            "author_id": document["author_id"],
            "summary": document["summary"],
            "status": document["status"],
            "created_date": document["created_date"],
            "confidentiality": document["confidentiality"],
        }
        for document in state["documents"]
        if document["id"] in visible_document_ids
    ]
    known_people = known_people_projection(game, actor_id)
    known_people_ids = {item["id"] for item in known_people}
    if scene:
        for participant in scene["participants"]:
            participant_id = participant["actor_id"]
            if participant_id in known_people_ids or participant_id == actor_id:
                continue
            known_people.append(_public_person_profile(game, actor_id, participant_id))
            known_people_ids.add(participant_id)
    runtime = state["actor_runtime"][actor_id]
    return {
        "date": state["current_date"],
        "actor": context,
        "known_people": known_people,
        "public_background": deepcopy(PUBLIC_REFERENCE_MATERIALS),
        "relationship_to_player": _relationship_band(int(state["relations"][actor_id])),
        "knowledge": _retrieve_actor_knowledge(runtime, scene),
        "memories": _retrieve_actor_memories(runtime, scene),
        "tasks": _retrieve_actor_tasks(runtime),
        "commitments": [
            deepcopy(item)
            for item in state.get("commitments", [])
            if actor_id in item.get("known_by_ids", [])
            or actor_id in {item.get("giver_id"), item.get("receiver_id")}
        ][-8:],
        "visible_documents": visible_documents,
        "scene": {
            "kind": scene["kind"],
            "title": scene["title"],
            "agenda": scene.get("agenda"),
            "participants": [item["actor_id"] for item in scene["participants"]],
            "transcript": [
                {"turn_id": item["id"], "speaker_id": item["speaker_id"], "text": item["text"]}
                for item in scene["transcript"][-24:]
            ],
        }
        if scene
        else None,
    }


def actor_available_knowledge_ids(game: StoredGame, actor_id: str) -> List[str]:
    game = hydrate_daily_actor_state(game)
    runtime_ids = [
        item["id"]
        for item in game.state["actor_runtime"][actor_id].get("knowledge", [])
        if item.get("status", "active") == "active"
    ]
    document_ids = [
        item["id"]
        for item in game.state["documents"]
        if item["author_id"] == actor_id or actor_id in item.get("recipient_ids", [])
    ]
    return list(dict.fromkeys(runtime_ids + document_ids + [item["id"] for item in PUBLIC_REFERENCE_MATERIALS]))


def _public_person_profile(game: StoredGame, observer_id: str, target_id: str) -> Dict[str, Any]:
    if target_id == "player":
        return {
            "id": "player",
            "name": game.player_name,
            "title": "岚州市委书记",
            "public_position": "主持市委全面工作。",
            "work_style": "依据亲历互动逐步判断。",
            "organizational_relationship": "当前场景参与者",
        }
    actor = ACTORS[target_id]
    return {
        "id": target_id,
        "name": actor["name"],
        "title": actor["title"],
        "public_position": actor["public_position"],
        "work_style": actor["work_style"],
        "organizational_relationship": "当前场景参与者",
    }


def _retrieve_actor_knowledge(runtime: Dict[str, Any], scene: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    participant_ids = {
        item["actor_id"] for item in scene.get("participants", [])
    } if scene else set()
    active = [item for item in runtime.get("knowledge", []) if item.get("status", "active") == "active"]
    ranked = sorted(
        enumerate(active),
        key=lambda pair: (
            any(item in participant_ids for item in pair[1].get("related_actor_ids", [])),
            pair[1].get("confidence") == "high",
            pair[0],
        ),
        reverse=True,
    )
    return [deepcopy(item) for _, item in ranked[:14]]


def _retrieve_actor_memories(runtime: Dict[str, Any], scene: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    participant_ids = {
        item["actor_id"] for item in scene.get("participants", [])
    } if scene else set()
    memories = list(runtime.get("memories", []))
    ranked = sorted(
        enumerate(memories),
        key=lambda pair: (
            any(item in participant_ids for item in pair[1].get("related_actor_ids", [])),
            int(pair[1].get("importance", 2)),
            pair[0],
        ),
        reverse=True,
    )
    return [deepcopy(item) for _, item in ranked[:10]]


def _retrieve_actor_tasks(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = [
        item
        for item in runtime.get("tasks", [])
        if item.get("status") not in {"completed", "canceled"}
    ]
    priority = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
    ranked = sorted(
        enumerate(tasks),
        key=lambda pair: (priority.get(str(pair[1].get("priority", "normal")), 2), pair[0]),
        reverse=True,
    )
    return [deepcopy(item) for _, item in ranked[:10]]


def to_daily_game_view(game: StoredGame) -> DailyGameView:
    game = hydrate_daily_actor_state(game)
    state = game.state
    metrics = [
        MetricView(
            id=metric_id,
            label=label,
            value=int(state["metrics"][metric_id]),
            description=description,
            higher_is_better=higher_is_better,
        )
        for metric_id, label, description, higher_is_better in METRIC_DEFINITIONS
    ]
    actors = [
        DailyActorView(
            id=actor_id,
            name=actor["name"],
            title=actor["title"],
            public_position=actor["public_position"],
            known_note=actor["known_note"],
            work_style=actor["work_style"],
            relation=int(state["relations"][actor_id]),
            availability="可协调" if state["actor_runtime"][actor_id]["workload"] < 3 else "任务较满",
            directory_group=ACTOR_DIRECTORY_GROUPS[actor_id],
        )
        for actor_id, actor in ACTORS.items()
    ]
    documents = [
        DocumentView(
            id=item["id"],
            version=int(item["version"]),
            title=item["title"],
            document_type=item["document_type"],
            author_id=item["author_id"],
            author_label=actor_label(item["author_id"]),
            status=item["status"],
            confidentiality=item["confidentiality"],
            created_date=item["created_date"],
            due_date=item.get("due_date"),
            summary=item["summary"],
            content=item["content"],
            recipient_ids=list(item["recipient_ids"]),
            source_document_ids=list(item["source_document_ids"]),
            formal_effect=item["formal_effect"],
            annotations=list(item["annotations"]),
        )
        for item in state["documents"]
        if "player" in item["recipient_ids"] or item["author_id"] == "player"
    ]
    calendar = [_calendar_view(item) for item in state["calendar"]]
    active_scene = ActiveSceneView(**_scene_view(state["active_scene"])) if state.get("active_scene") else None
    reserved_today = sum(
        int(item["action_cost"])
        for item in state["calendar"]
        if item["date"] == state["current_date"] and item["status"] in {"scheduled", "due"}
    )
    return DailyGameView(
        id=game.id,
        version=game.version,
        schema_version=SCHEMA_VERSION,
        player_name=game.player_name,
        background=state["background"],
        mode=game.mode,
        model=game.model,
        api_base=game.api_base,
        status=game.status,
        current_date=state["current_date"],
        day_number=int(state["day_number"]),
        day_phase=state["day_phase"],
        action_budget=ActionBudgetView(
            total=int(state["action_total"]),
            remaining=int(state["action_remaining"]),
            reserved_today=reserved_today,
        ),
        briefing=[BriefingItemView(**item) for item in state["briefing"]],
        calendar=calendar,
        documents=documents,
        actors=actors,
        reference_materials=[ReferenceMaterialView(**item) for item in PUBLIC_REFERENCE_MATERIALS],
        issues=[IssueView(**item) for item in state["issues"]],
        active_scene=active_scene,
        metrics=metrics,
        notifications=[NotificationView(**item) for item in state["notifications"][-8:]],
        activity=[ActivityView(**item) for item in state["activity"] if item.get("visible", True)][-24:],
        pending_tasks=[
            "{} · {}（{}）".format(
                ACTORS[item["author_id"]]["name"],
                item["title"],
                item["due_date"],
            )
            for item in state["document_tasks"]
            if item["status"] == "queued"
        ],
        action_catalog={
            "meeting_types": [
                {
                    "id": item_id,
                    "label": item["label"],
                    "description": item["formal_effect"],
                    "action_cost": item["cost"],
                }
                for item_id, item in MEETING_TYPES.items()
            ],
            "locations": [
                {
                    "id": item_id,
                    "label": item["label"],
                    "description": "可选择提前通知或四不两直；两种方式看到的材料和现场不同。",
                    "action_cost": 2,
                }
                for item_id, item in LOCATIONS.items()
            ],
        },
    )


def _apply_agent_tool_effects(
    state: Dict[str, Any],
    scene: Dict[str, Any],
    actor_id: str,
    effects: Sequence[AgentToolEffect],
    *,
    settlement: bool,
) -> None:
    allowed = {"create_document", "revise_document"}
    if settlement:
        allowed.update(
            {
                "record_memory",
                "record_knowledge",
                "record_todo",
                "record_relationship_impression",
                "record_commitment",
                "contact_actor",
                "request_information",
                "propose_action",
            }
        )
    for effect in effects:
        if effect.kind not in allowed:
            raise ValueError("人物 Agent 在当前阶段调用了未授权的写工具")
        payload = effect.payload
        if effect.kind == "create_document":
            document_id = str(payload["document_id"])
            if any(item["id"] == document_id for item in state["documents"]):
                raise ValueError("人物 Agent 创建了重复文件 ID")
            deliver_to_ids = list(dict.fromkeys(payload.get("deliver_to_ids", [])))
            if any(item not in ACTORS and item != "player" for item in deliver_to_ids):
                raise ValueError("人物 Agent 文件收件人无效")
            state["documents"].append(
                {
                    "id": document_id,
                    "version": 1,
                    "title": str(payload["title"]),
                    "document_type": str(payload["document_type"]),
                    "author_id": actor_id,
                    "status": "ready" if deliver_to_ids else "draft",
                    "confidentiality": "内部",
                    "created_date": state["current_date"],
                    "due_date": None,
                    "summary": str(payload["summary"]),
                    "content": str(payload["content"]),
                    "recipient_ids": list(dict.fromkeys([actor_id] + deliver_to_ids)),
                    "source_document_ids": list(payload.get("source_document_ids", [])),
                    "formal_effect": "人物工作草稿或就绪材料，未经相应签发和程序不形成正式决定。",
                    "annotations": [],
                    "handled_date": None,
                }
            )
            _add_activity(
                state,
                "agent_file",
                "{}形成工作材料".format(actor_label(actor_id)),
                "《{}》{}。".format(
                    payload["title"],
                    "已送达玩家" if "player" in deliver_to_ids else "保存在其私人工作区",
                ),
                visible="player" in deliver_to_ids,
            )
            continue
        if effect.kind == "revise_document":
            document = _find_by_id(state["documents"], str(payload["document_id"]))
            if document["author_id"] != actor_id or document["status"] not in {"draft", "returned", "ready"}:
                raise ValueError("人物 Agent 无权修改这份文件")
            document["summary"] = str(payload["summary"])
            document["content"] = str(payload["content"])
            document["version"] += 1
            continue
        if effect.kind == "record_knowledge":
            state["actor_runtime"][actor_id]["knowledge"].append(
                {
                    "id": _new_id(state, "knowledge"),
                    "claim": str(payload["claim"]),
                    "source": {
                        "type": payload.get("source_type", "inference"),
                        "id": payload.get("source_id"),
                    },
                    "acquired_date": state["current_date"],
                    "confidence": payload.get("confidence", "medium"),
                    "kind": "dynamic",
                    "status": "active",
                    "related_actor_ids": list(payload.get("related_actor_ids", [])),
                    "related_issue_ids": list(payload.get("related_issue_ids", [])),
                }
            )
            continue
        if effect.kind == "record_memory":
            state["actor_runtime"][actor_id]["memories"].append(
                {
                    "id": _new_id(state, "memory"),
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "memory_type": payload.get("memory_type", "episodic"),
                    "importance": int(payload.get("importance", 3)),
                    "summary": str(payload["summary"]),
                    "related_actor_ids": list(payload.get("related_actor_ids", [])),
                    "related_issue_ids": list(payload.get("related_issue_ids", [])),
                    "source_turn_ids": list(payload.get("source_turn_ids", [])),
                }
            )
            continue
        if effect.kind == "record_relationship_impression":
            target_id = str(payload["target_id"])
            relationship = state["actor_runtime"][actor_id]["relationships"].setdefault(
                target_id,
                {"score": 50, "last_updated": state["current_date"], "note": ""},
            )
            delta = 1 if payload.get("signal") == "improved" else -1 if payload.get("signal") == "strained" else 0
            relationship["score"] = max(0, min(100, int(relationship.get("score", 50)) + delta))
            relationship["last_updated"] = state["current_date"]
            relationship["note"] = str(payload["note"])
            relationship["related_issue_id"] = payload.get("related_issue_id")
            continue
        if effect.kind == "record_todo":
            state["actor_runtime"][actor_id]["tasks"].append(
                {
                    "id": _new_id(state, "todo"),
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "summary": str(payload["summary"]),
                    "due_date": payload.get("due_date"),
                    "priority": payload.get("priority", "normal"),
                    "requires_formal_decision": bool(payload.get("requires_formal_decision", False)),
                    "related_actor_ids": list(payload.get("related_actor_ids", [])),
                    "related_issue_ids": list(payload.get("related_issue_ids", [])),
                    "status": (
                        "awaiting_formal_decision"
                        if payload.get("requires_formal_decision")
                        else "planned"
                    ),
                }
            )
            continue
        if effect.kind == "record_commitment":
            visibility = str(payload.get("visibility", "private"))
            scene_people = [item["actor_id"] for item in scene["participants"]]
            if visibility == "public":
                known_by_ids = ["player"] + list(ACTORS)
            elif visibility in {"participants", "internal"}:
                known_by_ids = scene_people
            else:
                known_by_ids = [str(payload["giver_id"]), str(payload["receiver_id"])]
            state["commitments"].append(
                {
                    "id": _new_id(state, "commitment"),
                    "created_date": state["current_date"],
                    "scene_id": scene["id"],
                    "commitment_type": payload.get("commitment_type", "instruction"),
                    "giver_id": str(payload["giver_id"]),
                    "receiver_id": str(payload["receiver_id"]),
                    "summary": str(payload["summary"]),
                    "condition": payload.get("condition"),
                    "due_date": payload.get("due_date"),
                    "visibility": visibility,
                    "requires_formal_decision": bool(payload.get("requires_formal_decision", False)),
                    "formal_effect": "pending" if payload.get("requires_formal_decision") else "informal",
                    "status": "open",
                    "known_by_ids": list(dict.fromkeys(known_by_ids)),
                }
            )
            continue
        if effect.kind == "contact_actor":
            target_id = str(payload["target_id"])
            _add_activity(
                state,
                "agent_contact",
                "{}会后联络{}".format(actor_label(actor_id), actor_label(target_id)),
                str(payload["summary"]),
                visible=False,
            )
            state["actor_runtime"][target_id]["memories"].append(
                {
                    "id": _new_id(state, "memory"),
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "memory_type": "message",
                    "importance": 2,
                    "summary": "{}会后联系：{}".format(actor_label(actor_id), payload["summary"]),
                    "related_actor_ids": [actor_id],
                    "related_issue_ids": [],
                    "source_turn_ids": [],
                }
            )
            continue
        if effect.kind == "request_information":
            target_id = str(payload["target_id"])
            due = (_parse_date(state["current_date"]) + timedelta(days=1)).isoformat()
            state["document_tasks"].append(
                {
                    "id": _new_id(state, "task"),
                    "author_id": target_id,
                    "title": payload.get("title") or "会后信息核实材料",
                    "document_type": "briefing",
                    "instructions": "{}请求核实：{}".format(actor_label(actor_id), payload["summary"]),
                    "source_document_ids": [],
                    "created_date": state["current_date"],
                    "due_date": due,
                    "status": "queued",
                    "scene_id": scene["id"],
                }
            )
            state["actor_runtime"][target_id]["workload"] += 1
            continue
        if effect.kind == "propose_action":
            state["actor_runtime"][actor_id]["tasks"].append(
                {
                    "id": _new_id(state, "todo"),
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "summary": str(payload["summary"]),
                    "action_type": str(payload["action_type"]),
                    "target_ids": list(payload.get("target_ids", [])),
                    "due_date": payload.get("due_date"),
                    "priority": "normal",
                    "requires_formal_decision": bool(payload.get("requires_formal_decision", False)),
                    "status": (
                        "awaiting_formal_decision"
                        if payload.get("requires_formal_decision")
                        else "planned"
                    ),
                }
            )
            if payload.get("requires_formal_decision"):
                _add_notification(
                    state,
                    "会后行动建议待决",
                    "{}建议：{}。该事项尚未获得正式效力。".format(actor_label(actor_id), payload["summary"]),
                    "neutral",
                )


def _settle_scene(
    game: StoredGame,
    scene: Dict[str, Any],
    transcript_text: str,
    resolution: Optional[str],
    post_scene_results: Optional[Mapping[str, PostSceneResult]],
) -> None:
    state = game.state
    npc_ids = [
        item["actor_id"] for item in scene["participants"] if item["actor_id"] != "player"
    ]
    results = post_scene_results or {}
    memory = "{}：{}".format(scene["title"], _shorten(transcript_text.replace("\n", " "), 220))
    for actor_id in npc_ids:
        if actor_id in results:
            result = results[actor_id]
            _apply_agent_tool_effects(
                state,
                scene,
                actor_id,
                result.tool_effects,
                settlement=True,
            )
            if not any(effect.kind == "record_memory" for effect in result.tool_effects):
                state["actor_runtime"][actor_id]["memories"].append(
                    _fallback_memory(state, scene, result.memory)
                )
            _apply_post_scene_intents(state, scene, actor_id, result)
            if result.relationship_signal == "improved":
                state["relations"][actor_id] = min(100, int(state["relations"][actor_id]) + 1)
            elif result.relationship_signal == "strained":
                state["relations"][actor_id] = max(0, int(state["relations"][actor_id]) - 1)
            player_relationship = state["actor_runtime"][actor_id]["relationships"].setdefault(
                "player",
                {"score": 50, "last_updated": state["current_date"], "note": ""},
            )
            player_relationship["score"] = state["relations"][actor_id]
            player_relationship["last_updated"] = state["current_date"]
        else:
            state["actor_runtime"][actor_id]["memories"].append(
                _fallback_memory(state, scene, memory)
            )
    if scene["kind"] == "meeting":
        secretary_present = "secretary_general" in npc_ids
        if secretary_present:
            due = (_parse_date(state["current_date"]) + timedelta(days=1)).isoformat()
            state["document_tasks"].append(
                {
                    "id": _new_id(state, "task"),
                    "author_id": "secretary_general",
                    "title": "{}会议纪要".format(scene["title"]),
                    "document_type": "meeting_material",
                    "instructions": "根据冻结的会议记录整理主要意见、分歧、任务和正式效力。",
                    "source_document_ids": [],
                    "created_date": state["current_date"],
                    "due_date": due,
                    "status": "queued",
                    "scene_id": scene["id"],
                }
            )
        if "county_secretary" in npc_ids and "industry_vice_mayor" in npc_ids:
            _add_activity(
                state,
                "agent_contact",
                "会后通气",
                "高维民与邵文远在会后交换了对就业口径和产业窗口的判断。",
                visible=False,
            )
            state["actor_runtime"]["county_secretary"]["memories"].append(
                {
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "summary": "会后与邵文远通气，准备协调县企口径。",
                }
            )
    elif scene["kind"] in {"conversation", "superior_meeting"} and npc_ids:
        actor_id = npc_ids[0]
        if actor_id == "secretary_general" and any(word in transcript_text for word in ("起草", "报告", "材料")):
            due = (_parse_date(state["current_date"]) + timedelta(days=1)).isoformat()
            state["document_tasks"].append(
                {
                    "id": _new_id(state, "task"),
                    "author_id": actor_id,
                    "title": "根据书记面谈要求形成的工作材料",
                    "document_type": "briefing",
                    "instructions": _shorten(transcript_text, 700),
                    "source_document_ids": [],
                    "created_date": state["current_date"],
                    "due_date": due,
                    "status": "queued",
                    "scene_id": scene["id"],
                }
            )
        if actor_id == "county_secretary":
            _add_activity(
                state,
                "agent_contact",
                "面谈后联系",
                "高维民在面谈后联系了县政府有关负责人，要求重新准备就业口径说明。",
                visible=False,
            )
    if resolution:
        _add_activity(state, "resolution", "场景结论", resolution.strip())


def _fallback_memory(state: Dict[str, Any], scene: Dict[str, Any], summary: str) -> Dict[str, Any]:
    return {
        "id": _new_id(state, "memory"),
        "date": state["current_date"],
        "scene_id": scene["id"],
        "memory_type": "episodic",
        "importance": 3,
        "summary": summary,
        "related_actor_ids": [item["actor_id"] for item in scene["participants"]],
        "related_issue_ids": [],
        "source_turn_ids": [item["id"] for item in scene["transcript"][-12:]],
    }


def _apply_post_scene_intents(
    state: Dict[str, Any],
    scene: Dict[str, Any],
    actor_id: str,
    result: PostSceneResult,
) -> None:
    for intent in result.intents:
        if intent.kind == "none":
            continue
        if intent.kind == "contact_actor":
            if not intent.target_id or intent.target_id not in ACTORS or intent.target_id == actor_id:
                continue
            _add_activity(
                state,
                "agent_contact",
                "{}会后联络{}".format(actor_label(actor_id), actor_label(intent.target_id)),
                intent.summary,
                visible=False,
            )
            state["actor_runtime"][intent.target_id]["memories"].append(
                {
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "summary": "{}会后联系：{}".format(actor_label(actor_id), intent.summary),
                }
            )
            continue
        if intent.kind in {"draft_document", "request_information"}:
            due = (_parse_date(state["current_date"]) + timedelta(days=1)).isoformat()
            state["document_tasks"].append(
                {
                    "id": _new_id(state, "task"),
                    "author_id": actor_id,
                    "title": intent.title or ("会后核实材料" if intent.kind == "request_information" else "会后工作材料"),
                    "document_type": "briefing" if intent.kind == "request_information" else "report",
                    "instructions": intent.summary,
                    "source_document_ids": [],
                    "created_date": state["current_date"],
                    "due_date": due,
                    "status": "queued",
                    "scene_id": scene["id"],
                }
            )
            state["actor_runtime"][actor_id]["workload"] += 1
            continue
        if intent.kind == "propose_action":
            state["actor_runtime"][actor_id]["tasks"].append(
                {
                    "date": state["current_date"],
                    "scene_id": scene["id"],
                    "summary": intent.summary,
                    "status": "awaiting_formal_decision" if intent.requires_formal_decision else "planned",
                }
            )
            if intent.requires_formal_decision:
                _add_notification(
                    state,
                    "会后行动建议待决",
                    "{}建议：{}。该事项尚未获得正式效力。".format(actor_label(actor_id), intent.summary),
                    "neutral",
                )


def _settle_daily_world(game: StoredGame) -> None:
    state = game.state
    overdue = [
        task
        for task in state["document_tasks"]
        if task["status"] == "queued" and task["due_date"] < state["current_date"]
    ]
    if overdue:
        _change_metric(state, "admin", -1)
        _add_notification(
            state,
            "后台任务逾期",
            "有 {} 项材料未按预计日期完成，次日晨报将继续提醒。".format(len(overdue)),
            "warning",
        )
    for actor_id, runtime in state["actor_runtime"].items():
        if runtime["workload"] >= 3:
            _add_activity(
                state,
                "agent_intent",
                "{}选择压缩任务".format(ACTORS[actor_id]["name"]),
                "任务过载使部分工作被顺延或转为简略处理。",
                visible=False,
            )


def _complete_due_document_tasks(game: StoredGame) -> None:
    state = game.state
    for task in state["document_tasks"]:
        if task["status"] != "queued" or task["due_date"] > state["current_date"]:
            continue
        sources = [
            _find_by_id(state["documents"], document_id)
            for document_id in task["source_document_ids"]
        ]
        source_summary = "；".join(item["summary"] for item in sources)
        content = (
            "起草依据：{}\n\n工作要求：{}\n\n初步判断：现有材料仍需区分已核实事实、部门判断和待决事项。"
        ).format(source_summary or "面谈、会议记录和现有内部材料", task["instructions"])
        state["documents"].append(
            {
                "id": _new_id(state, "doc"),
                "version": 1,
                "title": task["title"],
                "document_type": task["document_type"],
                "author_id": task["author_id"],
                "status": "ready",
                "confidentiality": "内部",
                "created_date": state["current_date"],
                "due_date": None,
                "summary": _shorten(task["instructions"], 140),
                "content": content,
                "recipient_ids": ["player"],
                "source_document_ids": task["source_document_ids"],
                "formal_effect": "草稿，需玩家审阅、签发或转交后才可能产生进一步效力。",
                "annotations": [],
            }
        )
        task["status"] = "completed"
        state["actor_runtime"][task["author_id"]]["workload"] = max(
            0,
            int(state["actor_runtime"][task["author_id"]]["workload"]) - 1,
        )
        _add_notification(
            state,
            "新文件已送达",
            "{}完成《{}》，已进入收件箱。".format(ACTORS[task["author_id"]]["name"], task["title"]),
            "positive",
        )


def _resolve_delayed_triggers(game: StoredGame) -> None:
    state = game.state
    for trigger in state["delayed_triggers"]:
        if trigger["status"] != "scheduled":
            continue
        if trigger["expires_date"] < state["current_date"]:
            trigger["status"] = "expired"
            continue
        if trigger["due_date"] > state["current_date"]:
            continue
        if trigger["kind"] == "superior_document_reaction":
            document = _find_by_id(state["documents"], trigger["source_id"])
            if trigger.get("detail"):
                detail = "省委办公厅反馈：{}".format(trigger["detail"])
            else:
                has_data_note = any(
                    word in (document["content"] + " ".join(document["annotations"]))
                    for word in ("数据", "就业", "核实", "风险")
                )
                if has_data_note:
                    detail = "省委办公厅反馈：报告已收阅，请在三日内补充尚未核实的数据和责任节点。"
                    _change_metric(state, "org_credit", 1)
                else:
                    detail = "省委办公厅追问：报告缺少就业影响和数据来源，请重新补报。"
                    _change_metric(state, "org_credit", -2)
            if trigger.get("condition"):
                detail = "{}（此前关注条件：{}）".format(detail, trigger["condition"])
            _add_notification(state, "上级反馈", detail, "warning")
            state["documents"].append(
                {
                    "id": _new_id(state, "doc"),
                    "version": 1,
                    "title": "省委办公厅对报送材料的反馈",
                    "document_type": "notice",
                    "author_id": "superior",
                    "status": "received",
                    "confidentiality": "内部",
                    "created_date": state["current_date"],
                    "due_date": None,
                    "summary": detail,
                    "content": detail,
                    "recipient_ids": ["player"],
                    "source_document_ids": [document["id"]],
                    "formal_effect": "上级反馈，可能形成补报任务。",
                    "annotations": [],
                }
            )
            trigger["status"] = "triggered"


def _generate_dynamic_event(game: StoredGame) -> None:
    state = game.state
    rng = _rng(game, "external-event:{}".format(state["day_number"]))
    if rng.random() > 0.62:
        return
    candidates = [
        {
            "id": "video_followup",
            "title": "园区视频继续传播",
            "detail": "本地媒体开始追问夜间排放视频的拍摄时间，宣传部门建议先核实再回应。",
            "metric": ("social", -1),
        },
        {
            "id": "rain_warning",
            "title": "短时强降雨概率上升",
            "detail": "气象部门提高未来三天降雨风险提示，但是否形成灾情仍不确定。",
            "metric": ("flood", -1),
        },
        {
            "id": "credit_question",
            "title": "银行要求补充资产材料",
            "detail": "省城商行分行向企业发出补充材料通知，尚未决定是否调整授信。",
            "metric": ("employment", -1),
        },
        {
            "id": "county_revision",
            "title": "县里准备修订就业口径",
            "detail": "北山县内部开始重新汇总劳务与上下游人员，但尚未正式报送。",
            "metric": ("admin", 1),
        },
    ]
    event = deepcopy(rng.choice(candidates))
    if event["id"] in state["event_history"]:
        return
    state["event_history"].append(event["id"])
    metric_id, delta = event["metric"]
    _change_metric(state, metric_id, delta)
    _add_notification(state, event["title"], event["detail"], "warning")
    _add_activity(state, "external_event", event["title"], event["detail"])


def _assemble_briefing(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current = state["current_date"]
    if int(state["day_number"]) == 1:
        items.extend(
            [
                {
                    "id": "brief-news-park",
                    "category": "news",
                    "headline": "北山县召开产业转型推进会",
                    "summary": "公开报道未提具体停产范围；园区夜间排放视频正在传播。",
                    "source": "《岚州日报》与网络舆情监测",
                    "urgency": "high",
                    "document_id": None,
                    "calendar_entry_id": None,
                },
                {
                    "id": "brief-weather",
                    "category": "news",
                    "headline": "未来十天降水趋势提示",
                    "summary": "气象部门提示多雨概率上升，目前不构成确定灾情。",
                    "source": "市气象局",
                    "urgency": "normal",
                    "document_id": None,
                    "calendar_entry_id": None,
                },
            ]
        )
    for document in state["documents"]:
        if document["created_date"] != current and int(state["day_number"]) > 1:
            continue
        if "player" not in document["recipient_ids"] or document["status"] == "archived":
            continue
        category = "superior" if document["author_id"] == "superior" else (
            "request" if document["document_type"] == "request" else "report"
        )
        items.append(
            {
                "id": "brief-{}".format(document["id"]),
                "category": category,
                "headline": document["title"],
                "summary": document["summary"],
                "source": actor_label(document["author_id"]),
                "urgency": "high" if document.get("due_date") else "normal",
                "document_id": document["id"],
                "calendar_entry_id": None,
            }
        )
    for entry in state["calendar"]:
        if entry["date"] != current or entry["status"] not in {"scheduled", "due", "active"}:
            continue
        items.append(
            {
                "id": "brief-{}".format(entry["id"]),
                "category": "schedule",
                "headline": entry["title"],
                "summary": "当日日程，预计消耗 {} 个行动点。".format(entry["action_cost"]),
                "source": entry["source"],
                "urgency": "high" if entry["mandatory"] else "normal",
                "document_id": None,
                "calendar_entry_id": entry["id"],
            }
        )
    for notification in state["notifications"][-5:]:
        if notification["date"] != current:
            continue
        items.append(
            {
                "id": "brief-{}".format(notification["id"]),
                "category": "reminder",
                "headline": notification["title"],
                "summary": notification["detail"],
                "source": "日终结算",
                "urgency": "high" if notification["tone"] in {"warning", "danger"} else "normal",
                "document_id": None,
                "calendar_entry_id": None,
            }
        )
    deadline = next(
        (item["deadline"] for item in state["issues"] if item["id"] == "industry_rectification"),
        None,
    )
    if deadline and deadline >= current:
        days = (_parse_date(deadline) - _parse_date(current)).days
        items.append(
            {
                "id": "brief-deadline-industry",
                "category": "reminder",
                "headline": "上级简要情况报送期限",
                "summary": "距离报送期限还有 {} 天。".format(days),
                "source": "省委办公厅通知",
                "urgency": "critical" if days <= 1 else "high",
                "document_id": "doc-superior-notice",
                "calendar_entry_id": None,
            }
        )
    order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    return sorted(items, key=lambda item: (order[item["urgency"]], item["headline"]))[:18]


def _activate_next_due_schedule(game: StoredGame) -> None:
    state = game.state
    if state.get("active_scene"):
        return
    due = next(
        (
            item
            for item in state["calendar"]
            if item["date"] == state["current_date"] and item["status"] == "due"
        ),
        None,
    )
    if due is None:
        return
    if int(state["action_remaining"]) < int(due["action_cost"]):
        due["status"] = "conflict"
        _add_notification(
            state,
            "日程冲突",
            "“{}”到期，但当日行动点不足，需要改期或取消其他安排。".format(due["title"]),
            "danger",
        )
        return
    if due["kind"] == "meeting":
        _start_scheduled_meeting_in_place(game, due)
    elif due["kind"] == "field_visit":
        _start_scheduled_field_in_place(game, due)
    else:
        actor_id = due["participant_ids"][0] if due["participant_ids"] else "superior"
        _start_scheduled_conversation_in_place(game, due, actor_id)


def _start_scheduled_meeting_in_place(game: StoredGame, entry: Dict[str, Any]) -> None:
    state = game.state
    _spend_action_points(state, int(entry["action_cost"]))
    scene = _base_scene(
        state,
        "meeting",
        entry["title"],
        int(entry["action_cost"]),
        entry["id"],
    )
    meeting_type = entry.get("meeting_type") or "coordination"
    discussion_mode = entry.get("discussion_mode") or "chaired"
    scene.update(
        {
            "meeting_type": meeting_type,
            "discussion_mode": discussion_mode,
            "agenda": entry["title"],
            "participants": [_participant("player", "chair")]
            + [
                _participant(
                    actor_id,
                    "member" if actor_id in STANDING_COMMITTEE_MEMBER_IDS else "invitee",
                    can_vote=actor_id in STANDING_COMMITTEE_MEMBER_IDS,
                )
                for actor_id in entry["participant_ids"]
            ],
            "can_vote": meeting_type == "standing_committee"
            and _standing_committee_present_count(entry["participant_ids"]) >= 6,
        }
    )
    _append_transcript(scene, "system", "日程系统", "system", "预定日程已到，会议自动开始。")
    state["active_scene"] = scene
    state["day_phase"] = "scene_active"
    entry["status"] = "active"


def _start_scheduled_field_in_place(game: StoredGame, entry: Dict[str, Any]) -> None:
    state = game.state
    location_id = entry.get("location_id") or "beishan_park"
    _spend_action_points(state, int(entry["action_cost"]))
    scene = _base_scene(state, "field_visit", entry["title"], int(entry["action_cost"]), entry["id"])
    scene.update(
        {
            "location_id": location_id,
            "notified": bool(entry.get("notified", True)),
            "participants": [_participant("player", "chair")],
        }
    )
    _append_transcript(
        scene,
        "system",
        "现场观察",
        "system",
        _field_observation(game, location_id, bool(entry.get("notified", True))),
    )
    for belief_id in LOCATIONS[location_id]["reveals"]:
        if belief_id not in state["player_beliefs"]:
            state["player_beliefs"].append(belief_id)
    state["active_scene"] = scene
    state["day_phase"] = "scene_active"
    entry["status"] = "active"


def _start_scheduled_conversation_in_place(
    game: StoredGame,
    entry: Dict[str, Any],
    actor_id: str,
) -> None:
    state = game.state
    kind = "superior_meeting" if entry["kind"] == "superior_meeting" else "conversation"
    _spend_action_points(state, int(entry["action_cost"]))
    scene = _base_scene(state, kind, entry["title"], int(entry["action_cost"]), entry["id"])
    scene["participants"] = [_participant("player", "chair"), _participant(actor_id, "counterpart")]
    _append_transcript(scene, "system", "日程系统", "system", "预定日程已到，面谈自动开始。")
    state["active_scene"] = scene
    state["day_phase"] = "scene_active"
    entry["status"] = "active"


def _base_scene(
    state: Dict[str, Any],
    kind: str,
    title: str,
    action_cost: int,
    calendar_entry_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": _new_id(state, "scene"),
        "kind": kind,
        "title": title,
        "status": "active",
        "action_cost": action_cost,
        "record_version": 0,
        "meeting_type": None,
        "discussion_mode": None,
        "agenda": None,
        "location_id": None,
        "notified": None,
        "participants": [],
        "transcript": [],
        "generation": {
            "id": "idle",
            "status": "idle",
            "actor_id": None,
            "message": "",
        },
        "silence_count": 0,
        "can_vote": False,
        "vote_result": None,
        "calendar_entry_id": calendar_entry_id,
    }


def _append_transcript(
    scene: Dict[str, Any],
    speaker_id: str,
    speaker_name: str,
    speaker_type: str,
    text: str,
) -> None:
    scene["record_version"] += 1
    scene["transcript"].append(
        {
            "id": "turn-{}".format(scene["record_version"]),
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "speaker_type": speaker_type,
            "text": text,
            "record_version": scene["record_version"],
        }
    )


def _participant(actor_id: str, attendance_role: str, can_vote: bool = False) -> Dict[str, Any]:
    if actor_id == "player":
        return {
            "actor_id": "player",
            "name": "玩家",
            "title": "岚州市委书记",
            "attendance_role": attendance_role,
            "can_vote": True,
        }
    actor = ACTORS[actor_id]
    return {
        "actor_id": actor_id,
        "name": actor["name"],
        "title": actor["title"],
        "attendance_role": attendance_role,
        "can_vote": can_vote,
    }


def _scene_view(scene: Dict[str, Any]) -> Dict[str, Any]:
    generation = deepcopy(scene["generation"])
    generation.pop("started_record_version", None)
    return {
        "id": scene["id"],
        "kind": scene["kind"],
        "title": scene["title"],
        "status": scene["status"],
        "action_cost": scene["action_cost"],
        "record_version": scene["record_version"],
        "meeting_type": scene.get("meeting_type"),
        "discussion_mode": scene.get("discussion_mode"),
        "agenda": scene.get("agenda"),
        "location_id": scene.get("location_id"),
        "notified": scene.get("notified"),
        "participants": [SceneParticipantView(**item).model_dump() for item in scene["participants"]],
        "transcript": [TranscriptTurnView(**item).model_dump() for item in scene["transcript"]],
        "generation": GenerationView(**generation).model_dump(),
        "silence_count": scene.get("silence_count", 0),
        "can_vote": scene.get("can_vote", False),
        "vote_result": scene.get("vote_result"),
    }


def _calendar_view(entry: Dict[str, Any]) -> CalendarEntryView:
    return CalendarEntryView(
        id=entry["id"],
        date=entry["date"],
        kind=entry["kind"],
        title=entry["title"],
        participant_ids=list(entry["participant_ids"]),
        participant_labels=[actor_label(item) for item in entry["participant_ids"]],
        location_id=entry.get("location_id"),
        location_label=LOCATIONS.get(entry.get("location_id"), {}).get("label"),
        meeting_type=entry.get("meeting_type"),
        discussion_mode=entry.get("discussion_mode"),
        action_cost=int(entry["action_cost"]),
        mandatory=bool(entry["mandatory"]),
        status=entry["status"],
        source=entry["source"],
        notified=bool(entry.get("notified", True)),
    )


def _choose_free_speaker(
    game: StoredGame,
    scene: Dict[str, Any],
    participant_ids: Sequence[str],
) -> Optional[str]:
    round_index = len([item for item in scene["transcript"] if item["speaker_type"] == "npc"])
    candidates: List[str] = []
    last_speaker = scene["transcript"][-1]["speaker_id"] if scene["transcript"] else None
    for actor_id in participant_ids:
        rng = _rng(game, "speech-intent:{}:{}:{}".format(scene["id"], round_index, actor_id))
        threshold = 0.42
        if actor_id == last_speaker:
            threshold = 0.12
        if rng.random() < threshold:
            candidates.append(actor_id)
    if not candidates:
        return None
    rng = _rng(game, "speaker-choice:{}:{}".format(scene["id"], round_index))
    return rng.choice(candidates)


def _field_observation(game: StoredGame, location_id: str, notified: bool) -> str:
    location = LOCATIONS[location_id]
    base = location["notified"] if notified else location["unannounced"]
    rng = _rng(game, "field:{}:{}:{}".format(game.state["day_number"], location_id, notified))
    qualifier = rng.choice(
        [
            "你能直接确认一部分现场情况，但无法据此推断全市总体。",
            "现场材料与口头解释并不完全一致，仍需要后续核查。",
            "这次观察提供了新的线索，也受到时段和样本范围限制。",
        ]
    )
    return "{} {}".format(base, qualifier)


def _standing_committee_present_count(participant_ids: Sequence[str]) -> int:
    return 1 + len(
        {
            actor_id
            for actor_id in participant_ids
            if actor_id in STANDING_COMMITTEE_MEMBER_IDS and actor_id != "player"
        }
    )


def _validate_used_beliefs(
    game: StoredGame,
    actor_id: str,
    used_belief_ids: Sequence[str],
) -> None:
    allowed = set(actor_available_knowledge_ids(game, actor_id))
    if not set(used_belief_ids).issubset(allowed):
        raise ValueError("人物 Agent 引用了其认知范围外的信息")


def _validate_actor_ids(actor_ids: Sequence[str]) -> None:
    unknown = [item for item in actor_ids if item not in ACTORS]
    if unknown:
        raise ValueError("未知人物：{}".format("、".join(unknown)))


def _mark_calendar_active(state: Dict[str, Any], entry_id: Optional[str]) -> None:
    if entry_id:
        _find_by_id(state["calendar"], entry_id)["status"] = "active"


def _spend_action_points(state: Dict[str, Any], cost: int) -> None:
    if int(state["action_remaining"]) < cost:
        raise ValueError("今天剩余行动点不足")
    state["action_remaining"] -= cost


def _finish_command(game: StoredGame, key: str) -> StoredGame:
    game.version += 1
    game.state.setdefault("processed_keys", {})[key] = game.version
    if len(game.state["processed_keys"]) > 300:
        oldest = list(game.state["processed_keys"])[:-250]
        for item in oldest:
            game.state["processed_keys"].pop(item, None)
    if game.state.get("active_scene"):
        game.state["day_phase"] = "scene_active"
    elif game.state["day_phase"] not in {"settling", "reviewing"}:
        game.state["day_phase"] = "action"
    game.state["briefing"] = _assemble_briefing(game.state)
    return game


def _require_daily(game: StoredGame) -> None:
    if not is_daily_game(game):
        raise ValueError("这是旧版六回合存档，请新建逐日模拟存档")


def _require_daily_active(game: StoredGame) -> None:
    _require_daily(game)
    if game.status != "active":
        raise ValueError("本局已经结束")


def _require_can_start_scene(game: StoredGame) -> None:
    _require_daily_active(game)
    if game.state.get("active_scene"):
        raise ValueError("请先结束当前互动场景")


def _require_active_scene(game: StoredGame) -> None:
    _require_daily_active(game)
    if not game.state.get("active_scene"):
        raise ValueError("当前没有进行中的互动场景")


def _new_id(state: Dict[str, Any], prefix: str) -> str:
    state["id_counter"] = int(state.get("id_counter", 0)) + 1
    return "{}-{}".format(prefix, state["id_counter"])


def _find_by_id(items: Sequence[Dict[str, Any]], item_id: str) -> Dict[str, Any]:
    for item in items:
        if item["id"] == item_id:
            return item
    raise ValueError("没有找到对象 {}".format(item_id))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _rng(game: StoredGame, label: str) -> random.Random:
    return random.Random("{}:{}".format(game.seed, label))


def _change_metric(state: Dict[str, Any], metric_id: str, delta: int) -> None:
    state["metrics"][metric_id] = max(0, min(100, int(state["metrics"][metric_id]) + delta))


def _add_notification(state: Dict[str, Any], title: str, detail: str, tone: str) -> None:
    state["notifications"].append(
        {
            "id": _new_id(state, "notice"),
            "date": state["current_date"],
            "title": title,
            "detail": detail,
            "tone": tone,
        }
    )


def _add_activity(
    state: Dict[str, Any],
    kind: str,
    title: str,
    summary: str,
    visible: bool = True,
) -> None:
    state["activity"].append(
        {
            "id": _new_id(state, "activity"),
            "date": state["current_date"],
            "kind": kind,
            "title": title,
            "summary": summary,
            "visible": visible,
        }
    )


def _shorten(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


def _relationship_band(value: int) -> str:
    if value >= 66:
        return "信任较高，愿意主动提供坏消息"
    if value >= 53:
        return "合作积极，但仍会保护职责边界"
    if value >= 43:
        return "仍在观察玩家风格"
    if value >= 32:
        return "有所保留，倾向采用正式口径"
    return "关系紧张，优先自保并减少非必要披露"
