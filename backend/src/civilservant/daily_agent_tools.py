from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .daily_models import AgentToolCall, AgentToolEffect
from .daily_scenario import (
    ACTORS,
    actor_acquaintance_ids,
    actor_organizational_relationship,
)
from .models import StoredGame




class _ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ContactListArgs(_ToolArgs):
    query: str = Field(default="", max_length=120)


class _FileListArgs(_ToolArgs):
    query: str = Field(default="", max_length=120)
    status: Optional[str] = Field(default=None, max_length=32)


class _FileReadArgs(_ToolArgs):
    document_id: str = Field(min_length=1, max_length=160)


class _FileWriteArgs(_ToolArgs):
    title: str = Field(min_length=2, max_length=160)
    document_type: Literal["report", "briefing", "request", "meeting_material", "note", "draft"] = (
        "briefing"
    )
    summary: str = Field(min_length=2, max_length=400)
    content: str = Field(min_length=2, max_length=8000)
    source_document_ids: List[str] = Field(default_factory=list, max_length=12)
    deliver_to_ids: List[str] = Field(default_factory=list, max_length=8)


class _FileReviseArgs(_ToolArgs):
    document_id: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=2, max_length=400)
    content: str = Field(min_length=2, max_length=8000)


class _MemoryListArgs(_ToolArgs):
    query: str = Field(default="", max_length=120)
    limit: int = Field(default=8, ge=1, le=20)


class _SceneListArgs(_ToolArgs):
    query: str = Field(default="", max_length=120)


class _SceneReadArgs(_ToolArgs):
    scene_id: str = Field(min_length=1, max_length=160)


class _NoArgs(_ToolArgs):
    pass


class _MemoryWriteArgs(_ToolArgs):
    summary: str = Field(min_length=2, max_length=600)
    memory_type: str = Field(default="episodic", max_length=32)
    importance: int = Field(default=3, ge=1, le=5)
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)
    source_turn_ids: List[str] = Field(default_factory=list, max_length=20)


class _KnowledgeWriteArgs(_ToolArgs):
    claim: str = Field(min_length=2, max_length=800)
    source_type: Literal["transcript", "document", "observation", "hearsay", "inference"]
    source_id: Optional[str] = Field(default=None, max_length=160)
    confidence: Literal["low", "medium", "high"] = "medium"
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)


class _RelationshipArgs(_ToolArgs):
    target_id: str = Field(min_length=1, max_length=128)
    signal: Literal["improved", "unchanged", "strained"]
    note: str = Field(min_length=2, max_length=400)
    related_issue_id: Optional[str] = Field(default=None, max_length=128)


class _TodoWriteArgs(_ToolArgs):
    summary: str = Field(min_length=2, max_length=500)
    due_date: Optional[str] = Field(default=None, max_length=10)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    requires_formal_decision: bool = False
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)


class _CommitmentArgs(_ToolArgs):
    commitment_type: Literal["instruction", "promise", "conditional_exchange", "reporting_duty"] = (
        "instruction"
    )
    giver_id: str = Field(min_length=1, max_length=128)
    receiver_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=2, max_length=600)
    condition: Optional[str] = Field(default=None, max_length=400)
    due_date: Optional[str] = Field(default=None, max_length=10)
    visibility: Literal["private", "participants", "internal", "public"] = "private"
    requires_formal_decision: bool = False


class _ContactArgs(_ToolArgs):
    target_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=2, max_length=500)


class _InformationArgs(_ContactArgs):
    title: Optional[str] = Field(default=None, max_length=160)


class _ActionArgs(_ToolArgs):
    summary: str = Field(min_length=2, max_length=500)
    action_type: str = Field(min_length=2, max_length=128)
    target_ids: List[str] = Field(default_factory=list, max_length=12)
    due_date: Optional[str] = Field(default=None, max_length=10)
    requires_formal_decision: bool = False


def agent_tool_catalog(phase: str) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = [
        _tool("list_contacts", "列出本人物认识的干部和利益相关方基本资料。", _ContactListArgs),
        _tool("list_visible_files", "列出本人物有权访问的游戏内文件。", _FileListArgs),
        _tool("read_file", "读取一份有权限文件的完整正文、批注和来源。", _FileReadArgs),
        _tool(
            "write_file",
            "新建本人物署名的游戏内草稿；deliver_to_ids非空时同时形成送达指定对象的就绪材料。",
            _FileWriteArgs,
        ),
        _tool("revise_file", "修改本人物仍可修订的草稿或退回文件。", _FileReviseArgs),
        _tool("list_memories", "按关键词检索本人物自己的记忆。", _MemoryListArgs),
        _tool("list_scene_records", "列出本人物亲历过的已冻结谈话和会议记录。", _SceneListArgs),
        _tool("read_scene_record", "读取本人物亲历过的一次完整冻结记录。", _SceneReadArgs),
        _tool("list_todos", "列出本人物尚未完成的待办。", _NoArgs),
    ]
    if phase == "settlement":
        tools.extend(
            [
                _tool(
                    "record_knowledge",
                    "把本场景中新获得、推断或听说的一项信息写入动态认知，并保留来源与置信度。"
                    "source_type 取值：transcript（本场景或亲历归档中的发言原文，source_id 填对应 turn_id）、"
                    "document（来自可见文件，source_id 填文件 id）、observation（本人亲历观察，source_id 填对应发言 turn_id）、"
                    "hearsay（从某次发言转述得知，可填对应 turn_id 也可不填）、inference（本人推断，不填 source_id）。",
                    _KnowledgeWriteArgs,
                ),
                _tool(
                    "record_memory",
                    "把本次亲历形成的私人记忆写入自己的记忆库。related_issue_ids 只能填上下文中 issues 列表里的 id，"
                    "没有对应议题就不要填。",
                    _MemoryWriteArgs,
                ),
                _tool(
                    "record_todo",
                    "记录本人准备跟进的待办，不自动取得正式决策效力。related_issue_ids 只能填上下文中 issues 列表里的 id，"
                    "没有对应议题就不要填。",
                    _TodoWriteArgs,
                ),
                _tool(
                    "record_relationship_impression",
                    "记录本人物对一名亲历对象的工作关系印象变化；只改变本人物的主观看法。"
                    "related_issue_id 只能填上下文中 issues 列表里的 id，没有对应议题就不要填。",
                    _RelationshipArgs,
                ),
                _tool(
                    "record_commitment",
                    "记录本场景中实际形成的交办、承诺或条件交换及其正式效力边界。",
                    _CommitmentArgs,
                ),
                _tool("contact_actor", "申请会后联系一名认识的人；只展开一跳。", _ContactArgs),
                _tool("request_information", "申请向认识的人或机构核实信息。", _InformationArgs),
                _tool(
                    "propose_action",
                    "提出权限内准备或需要正式决定的行动意图。",
                    _ActionArgs,
                ),
            ]
        )
    return tools


def execute_agent_tool(
    game: StoredGame,
    actor_id: str,
    phase: str,
    call: AgentToolCall,
    staged_effects: Sequence[AgentToolEffect],
) -> Tuple[Dict[str, Any], Optional[AgentToolEffect]]:
    try:
        if call.name == "list_contacts":
            query = _ContactListArgs.model_validate(call.arguments).query.strip()
            contacts = _known_people(game, actor_id)
            if query:
                filtered = [item for item in contacts if query in " ".join(str(value) for value in item.values())]
                # 过滤为空时回退全量名单，避免模型在不知道名字的情况下反复猜 query 走进死胡同。
                if filtered:
                    contacts = filtered
            return _ok(call, contacts[:40]), None
        if call.name == "list_visible_files":
            args = _FileListArgs.model_validate(call.arguments)
            documents = _visible_documents(game, actor_id, staged_effects)
            if args.query:
                documents = [item for item in documents if args.query in (item["title"] + " " + item["summary"])]
            if args.status:
                documents = [item for item in documents if item["status"] == args.status]
            return _ok(call, [_document_metadata(item) for item in documents[:30]]), None
        if call.name == "read_file":
            args = _FileReadArgs.model_validate(call.arguments)
            document = _find_visible_document(game, actor_id, args.document_id, staged_effects)
            return _ok(call, deepcopy(document)), None
        if call.name == "write_file":
            args = _FileWriteArgs.model_validate(call.arguments)
            _validate_sources(game, actor_id, args.source_document_ids, staged_effects)
            _validate_recipients(actor_id, args.deliver_to_ids)
            number = 1 + sum(effect.kind == "create_document" for effect in staged_effects)
            document_id = "agent-doc-{}-{}-{}".format(actor_id, game.version, number)
            effect = AgentToolEffect(
                kind="create_document",
                payload={
                    "document_id": document_id,
                    "title": args.title,
                    "document_type": args.document_type,
                    "summary": args.summary,
                    "content": args.content,
                    "source_document_ids": list(args.source_document_ids),
                    "deliver_to_ids": list(dict.fromkeys(args.deliver_to_ids)),
                },
            )
            return _ok(call, {"document_id": document_id, "staged": True}), effect
        if call.name == "revise_file":
            args = _FileReviseArgs.model_validate(call.arguments)
            document = _find_visible_document(game, actor_id, args.document_id, staged_effects)
            if document["author_id"] != actor_id or document["status"] not in {"draft", "returned", "ready"}:
                raise ValueError("只能修改本人尚未锁定的草稿、退回件或就绪材料")
            effect = AgentToolEffect(
                kind="revise_document",
                payload={"document_id": args.document_id, "summary": args.summary, "content": args.content},
            )
            return _ok(call, {"document_id": args.document_id, "staged": True}), effect
        if call.name == "list_memories":
            args = _MemoryListArgs.model_validate(call.arguments)
            memories = list(game.state["actor_runtime"][actor_id].get("memories", []))
            if args.query:
                memories = [item for item in memories if args.query in str(item.get("summary", ""))]
            return _ok(call, memories[-args.limit :]), None
        if call.name == "list_scene_records":
            query = _SceneListArgs.model_validate(call.arguments).query.strip()
            records = [
                item
                for item in game.state.get("scene_archive", [])
                if actor_id in {participant["actor_id"] for participant in item["participants"]}
            ]
            if query:
                records = [
                    item
                    for item in records
                    if query in (item["title"] + " " + str(item.get("agenda") or ""))
                ]
            data = [
                {
                    "scene_id": item["id"],
                    "title": item["title"],
                    "kind": item["kind"],
                    "closed_date": item.get("closed_date"),
                    "resolution": item.get("resolution"),
                }
                for item in records[-20:]
            ]
            return _ok(call, data), None
        if call.name == "read_scene_record":
            scene_id = _SceneReadArgs.model_validate(call.arguments).scene_id
            record = next(
                (
                    item
                    for item in game.state.get("scene_archive", [])
                    if item["id"] == scene_id
                    and actor_id in {participant["actor_id"] for participant in item["participants"]}
                ),
                None,
            )
            if record is None:
                raise ValueError("记录不存在或本人物没有亲历")
            return _ok(
                call,
                {
                    "scene_id": record["id"],
                    "title": record["title"],
                    "agenda": record.get("agenda"),
                    "closed_date": record.get("closed_date"),
                    "resolution": record.get("resolution"),
                    "meeting_materials": [
                        {
                            "document_id": item["document_id"],
                            "document_version": item["document_version"],
                            "title": item["title"],
                            "author_id": item["author_id"],
                            "summary": item["summary"],
                            "content": item["content"],
                            "formal_effect": item["formal_effect"],
                            "distribution_kind": item["distribution_kind"],
                        }
                        for item in record.get("meeting_materials", [])
                        if actor_id in item.get("audience_ids", [])
                    ],
                    "transcript": [
                        {
                            "turn_id": item["id"],
                            "speaker_id": item["speaker_id"],
                            "text": item["text"],
                        }
                        for item in record["transcript"]
                    ],
                },
            ), None
        if call.name == "list_todos":
            _NoArgs.model_validate(call.arguments)
            todos = [
                item
                for item in game.state["actor_runtime"][actor_id].get("tasks", [])
                if item.get("status") not in {"completed", "canceled"}
            ]
            return _ok(call, todos[-20:]), None
        if phase != "settlement":
            raise ValueError("这个工具只允许在场景结算阶段使用")
        if call.name == "record_knowledge":
            args = _KnowledgeWriteArgs.model_validate(call.arguments)
            _validate_related_ids(game, args.related_actor_ids, args.related_issue_ids)
            _validate_knowledge_source(game, actor_id, args.source_type, args.source_id, staged_effects)
            effect = AgentToolEffect(kind="record_knowledge", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name == "record_memory":
            args = _MemoryWriteArgs.model_validate(call.arguments)
            _validate_related_ids(game, args.related_actor_ids, args.related_issue_ids)
            _validate_source_turns(game, args.source_turn_ids)
            effect = AgentToolEffect(kind="record_memory", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name == "record_todo":
            args = _TodoWriteArgs.model_validate(call.arguments)
            _validate_due_date(game, args.due_date)
            _validate_related_ids(game, args.related_actor_ids, args.related_issue_ids)
            effect = AgentToolEffect(kind="record_todo", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name == "record_relationship_impression":
            args = _RelationshipArgs.model_validate(call.arguments)
            _validate_contact_for_relationship(game, actor_id, args.target_id)
            if args.related_issue_id:
                _validate_related_ids(game, [], [args.related_issue_id])
            effect = AgentToolEffect(kind="record_relationship_impression", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name == "record_commitment":
            args = _CommitmentArgs.model_validate(call.arguments)
            _validate_due_date(game, args.due_date)
            _validate_commitment_participants(game, actor_id, args.giver_id, args.receiver_id)
            effect = AgentToolEffect(kind="record_commitment", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name in {"contact_actor", "request_information"}:
            args = (
                _InformationArgs.model_validate(call.arguments)
                if call.name == "request_information"
                else _ContactArgs.model_validate(call.arguments)
            )
            _validate_contact(actor_id, args.target_id)
            effect = AgentToolEffect(kind=call.name, payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        if call.name == "propose_action":
            args = _ActionArgs.model_validate(call.arguments)
            _validate_due_date(game, args.due_date)
            for target_id in args.target_ids:
                if target_id not in ACTORS and target_id != "player":
                    raise ValueError("行动对象不在人物目录中")
            effect = AgentToolEffect(kind="propose_action", payload=args.model_dump())
            return _ok(call, {"staged": True}), effect
        raise ValueError("未知工具")
    except (ValidationError, ValueError, KeyError) as exc:
        return {
            "call_id": call.call_id,
            "name": call.name,
            "ok": False,
            "error": str(exc),
        }, None


def _tool(name: str, description: str, arguments_model: type[BaseModel]) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": arguments_model.model_json_schema(),
        },
    }


def _ok(call: AgentToolCall, data: Any) -> Dict[str, Any]:
    return {"call_id": call.call_id, "name": call.name, "ok": True, "data": data}


def _known_people(game: StoredGame, actor_id: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    relationships = game.state["actor_runtime"][actor_id].get("relationships", {})
    for target_id in actor_acquaintance_ids(actor_id):
        subjective = relationships.get(target_id, {"score": 50, "note": "尚无足够亲历判断。"})
        if target_id == "player":
            result.append(
                {
                    "id": "player",
                    "name": game.player_name,
                    "title": "岚州市委书记",
                    "public_position": "主持市委全面工作。",
                    "work_style": "仍由本人物根据亲历互动逐步判断。",
                    "organizational_relationship": actor_organizational_relationship(actor_id, target_id),
                    "working_relationship": _relationship_label(int(subjective.get("score", 50))),
                    "relationship_note": subjective.get("note", ""),
                }
            )
            continue
        target = ACTORS[target_id]
        result.append(
            {
                "id": target_id,
                "name": target["name"],
                "title": target["title"],
                "public_position": target["public_position"],
                "work_style": target["work_style"],
                "organizational_relationship": actor_organizational_relationship(actor_id, target_id),
                "working_relationship": _relationship_label(int(subjective.get("score", 50))),
                "relationship_note": subjective.get("note", ""),
            }
        )
    return result


def known_people_projection(game: StoredGame, actor_id: str) -> List[Dict[str, Any]]:
    return _known_people(game, actor_id)


def _relationship_label(score: int) -> str:
    if score >= 66:
        return "信任较高"
    if score >= 53:
        return "合作较顺畅"
    if score >= 43:
        return "一般工作关系"
    if score >= 32:
        return "有所保留"
    return "关系紧张"


def _visible_documents(
    game: StoredGame,
    actor_id: str,
    staged_effects: Sequence[AgentToolEffect],
) -> List[Dict[str, Any]]:
    documents = [deepcopy(item) for item in game.state["documents"]]
    scene = game.state.get("active_scene")
    if scene and scene.get("kind") == "meeting" and actor_id in {
        item["actor_id"] for item in scene.get("participants", [])
    }:
        for material in scene.get("meeting_materials", []):
            if actor_id not in material.get("audience_ids", []):
                continue
            snapshot = _meeting_material_document(material)
            documents = [item for item in documents if item["id"] != snapshot["id"]]
            documents.append(snapshot)
    for effect in staged_effects:
        if effect.kind == "create_document":
            payload = effect.payload
            deliver_to_ids = list(payload.get("deliver_to_ids", []))
            documents.append(
                {
                    "id": payload["document_id"],
                    "version": 1,
                    "title": payload["title"],
                    "document_type": payload["document_type"],
                    "author_id": actor_id,
                    "status": "ready" if deliver_to_ids else "draft",
                    "confidentiality": "内部",
                    "created_date": game.state["current_date"],
                    "due_date": None,
                    "summary": payload["summary"],
                    "content": payload["content"],
                    "recipient_ids": list(dict.fromkeys([actor_id] + deliver_to_ids)),
                    "source_document_ids": list(payload.get("source_document_ids", [])),
                    "formal_effect": "Agent工作草稿或就绪材料，不自动形成正式决定。",
                    "annotations": [],
                }
            )
        elif effect.kind == "revise_document":
            document = next((item for item in documents if item["id"] == effect.payload["document_id"]), None)
            if document:
                document["summary"] = effect.payload["summary"]
                document["content"] = effect.payload["content"]
                document["version"] = int(document["version"]) + 1
    return [
        item
        for item in documents
        if item["author_id"] == actor_id or actor_id in item.get("recipient_ids", [])
    ]


def _meeting_material_document(material: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": material["document_id"],
        "version": material["document_version"],
        "title": material["title"],
        "document_type": material["document_type"],
        "author_id": material["author_id"],
        "status": material["status"],
        "confidentiality": material["confidentiality"],
        "created_date": material["created_date"],
        "due_date": material.get("due_date"),
        "summary": material["summary"],
        "content": material["content"],
        "recipient_ids": list(material.get("audience_ids", [])),
        "source_document_ids": list(material["source_document_ids"]),
        "formal_effect": material["formal_effect"],
        "annotations": list(material["annotations"]),
        "meeting_distribution": material["distribution_kind"],
    }


def _find_visible_document(
    game: StoredGame,
    actor_id: str,
    document_id: str,
    staged_effects: Sequence[AgentToolEffect],
) -> Dict[str, Any]:
    visible = _visible_documents(game, actor_id, staged_effects)
    document = next((item for item in visible if item["id"] == document_id), None)
    if document is None:
        if not visible:
            raise ValueError(
                "本人物当前没有可见文件，无法读取任何文件；先 list_visible_files 确认，不要凭想象构造文件 ID。"
            )
        raise ValueError("文件不存在或本人物无权读取")
    return document


def _document_metadata(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": document["id"],
        "version": document["version"],
        "title": document["title"],
        "document_type": document["document_type"],
        "author_id": document["author_id"],
        "status": document["status"],
        "created_date": document["created_date"],
        "summary": document["summary"],
    }


def _validate_sources(
    game: StoredGame,
    actor_id: str,
    document_ids: Sequence[str],
    staged_effects: Sequence[AgentToolEffect],
) -> None:
    for document_id in document_ids:
        _find_visible_document(game, actor_id, document_id, staged_effects)


def _validate_recipients(actor_id: str, recipient_ids: Sequence[str]) -> None:
    known = set(actor_acquaintance_ids(actor_id)) | {actor_id, "player"}
    if any(item not in known for item in recipient_ids):
        raise ValueError("不能把文件直接送给本人物不认识或无渠道联系的对象")


def _validate_contact(actor_id: str, target_id: str) -> None:
    if target_id == actor_id or target_id not in actor_acquaintance_ids(actor_id):
        raise ValueError("联系对象不是本人物可用的工作联系人")


def _validate_related_ids(
    game: StoredGame,
    actor_ids: Sequence[str],
    issue_ids: Sequence[str],
) -> None:
    if any(item not in ACTORS and item != "player" for item in actor_ids):
        raise ValueError("记忆或待办引用了未知人物")
    known_issue_ids = {item["id"] for item in game.state["issues"]}
    if any(item not in known_issue_ids for item in issue_ids):
        raise ValueError("记忆或待办引用了未知议题")


def _validate_source_turns(game: StoredGame, turn_ids: Sequence[str]) -> None:
    scene = game.state.get("active_scene")
    known_turns = {item["id"] for item in scene["transcript"]} if scene else set()
    if any(item not in known_turns for item in turn_ids):
        raise ValueError("记忆引用了不在当前亲历记录中的发言")


def _validate_due_date(game: StoredGame, due_date: Optional[str]) -> None:
    if due_date is None:
        return
    parsed = date.fromisoformat(due_date)
    if parsed < date.fromisoformat(game.state["current_date"]):
        raise ValueError("期限不能早于当前日期")


def _validate_commitment_participants(
    game: StoredGame,
    actor_id: str,
    giver_id: str,
    receiver_id: str,
) -> None:
    allowed_people = set(ACTORS) | {"player"}
    if giver_id not in allowed_people or receiver_id not in allowed_people or giver_id == receiver_id:
        raise ValueError("承诺双方无效")
    scene = game.state.get("active_scene")
    scene_people = {item["actor_id"] for item in scene["participants"]} if scene else set()
    if actor_id not in {giver_id, receiver_id} and not {giver_id, receiver_id}.issubset(scene_people):
        raise ValueError("本人物没有亲历或参与这项承诺")


def _validate_knowledge_source(
    game: StoredGame,
    actor_id: str,
    source_type: str,
    source_id: Optional[str],
    staged_effects: Sequence[AgentToolEffect],
) -> None:
    if source_type in {"inference", "hearsay"} and source_id is None:
        return
    if source_id is None:
        raise ValueError("这种认知来源必须提供 source_id")
    if source_type in {"transcript", "observation", "hearsay"}:
        _validate_source_turns(game, [source_id])
        return
    if source_type == "document":
        _find_visible_document(game, actor_id, source_id, staged_effects)


def _validate_contact_for_relationship(game: StoredGame, actor_id: str, target_id: str) -> None:
    if target_id == actor_id:
        raise ValueError("不能记录与自己的关系")
    scene = game.state.get("active_scene")
    scene_people = {item["actor_id"] for item in scene["participants"]} if scene else set()
    if target_id not in actor_acquaintance_ids(actor_id) and target_id not in scene_people:
        raise ValueError("关系对象不是本人物认识或本场景亲历的人")
