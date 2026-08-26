from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from .daily_models import AgentToolCall, AgentToolEffect
from .daily_scenario import (
    ACTORS,
    actor_acquaintance_ids,
    actor_organizational_relationship,
)
from .models import StoredGame




class _FileListArgs(BaseModel):
    query: str = Field(default="", max_length=120)
    status: Optional[str] = Field(default=None, max_length=32)


class _FileReadArgs(BaseModel):
    document_id: str = Field(min_length=1, max_length=160)


class _FileWriteArgs(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    document_type: str = Field(default="briefing", max_length=48)
    summary: str = Field(min_length=2, max_length=400)
    content: str = Field(min_length=2, max_length=8000)
    source_document_ids: List[str] = Field(default_factory=list, max_length=12)
    deliver_to_ids: List[str] = Field(default_factory=list, max_length=8)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        allowed = {"report", "briefing", "request", "meeting_material", "note", "draft"}
        if value not in allowed:
            raise ValueError("不支持的文件类型")
        return value


class _FileReviseArgs(BaseModel):
    document_id: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=2, max_length=400)
    content: str = Field(min_length=2, max_length=8000)


class _MemoryListArgs(BaseModel):
    query: str = Field(default="", max_length=120)
    limit: int = Field(default=8, ge=1, le=20)


class _MemoryWriteArgs(BaseModel):
    summary: str = Field(min_length=2, max_length=600)
    memory_type: str = Field(default="episodic", max_length=32)
    importance: int = Field(default=3, ge=1, le=5)
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)
    source_turn_ids: List[str] = Field(default_factory=list, max_length=20)


class _KnowledgeWriteArgs(BaseModel):
    claim: str = Field(min_length=2, max_length=800)
    source_type: str = Field(max_length=32)
    source_id: Optional[str] = Field(default=None, max_length=160)
    confidence: str = Field(default="medium", max_length=16)
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in {"transcript", "document", "observation", "hearsay", "inference"}:
            raise ValueError("未知的信息来源类型")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        if value not in {"low", "medium", "high"}:
            raise ValueError("未知的置信度")
        return value


class _RelationshipArgs(BaseModel):
    target_id: str = Field(min_length=1, max_length=128)
    signal: str = Field(max_length=16)
    note: str = Field(min_length=2, max_length=400)
    related_issue_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str) -> str:
        if value not in {"improved", "unchanged", "strained"}:
            raise ValueError("未知的关系变化信号")
        return value


class _TodoWriteArgs(BaseModel):
    summary: str = Field(min_length=2, max_length=500)
    due_date: Optional[str] = Field(default=None, max_length=10)
    priority: str = Field(default="normal", max_length=16)
    requires_formal_decision: bool = False
    related_actor_ids: List[str] = Field(default_factory=list, max_length=12)
    related_issue_ids: List[str] = Field(default_factory=list, max_length=12)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in {"low", "normal", "high", "urgent"}:
            raise ValueError("未知的待办优先级")
        return value


class _CommitmentArgs(BaseModel):
    commitment_type: str = Field(default="instruction", max_length=32)
    giver_id: str = Field(min_length=1, max_length=128)
    receiver_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=2, max_length=600)
    condition: Optional[str] = Field(default=None, max_length=400)
    due_date: Optional[str] = Field(default=None, max_length=10)
    visibility: str = Field(default="private", max_length=32)
    requires_formal_decision: bool = False

    @field_validator("commitment_type")
    @classmethod
    def validate_commitment_type(cls, value: str) -> str:
        if value not in {"instruction", "promise", "conditional_exchange", "reporting_duty"}:
            raise ValueError("未知的承诺类型")
        return value

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, value: str) -> str:
        if value not in {"private", "participants", "internal", "public"}:
            raise ValueError("未知的知情范围")
        return value


class _ContactArgs(BaseModel):
    target_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=2, max_length=500)


class _InformationArgs(_ContactArgs):
    title: Optional[str] = Field(default=None, max_length=160)


class _ActionArgs(BaseModel):
    summary: str = Field(min_length=2, max_length=500)
    action_type: str = Field(min_length=2, max_length=128)
    target_ids: List[str] = Field(default_factory=list, max_length=12)
    due_date: Optional[str] = Field(default=None, max_length=10)
    requires_formal_decision: bool = False


def agent_tool_catalog(phase: str) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = [
        _tool("list_contacts", "列出本人物认识的干部和利益相关方基本资料。", {"query": "string，可选"}),
        _tool("list_visible_files", "列出本人物有权访问的游戏内文件。", {"query": "string，可选", "status": "string|null"}),
        _tool("read_file", "读取一份有权限文件的完整正文、批注和来源。", {"document_id": "string"}),
        _tool(
            "write_file",
            "新建本人物署名的游戏内草稿；deliver_to_ids非空时同时形成送达指定对象的就绪材料。",
            {
                "title": "string",
                "document_type": "report|briefing|request|meeting_material|note|draft",
                "summary": "string",
                "content": "string",
                "source_document_ids": ["document_id"],
                "deliver_to_ids": ["player或认识的actor_id"],
            },
        ),
        _tool("revise_file", "修改本人物仍可修订的草稿或退回文件。", {"document_id": "string", "summary": "string", "content": "string"}),
        _tool("list_memories", "按关键词检索本人物自己的记忆。", {"query": "string，可选", "limit": "1-20"}),
        _tool("list_scene_records", "列出本人物亲历过的已冻结谈话和会议记录。", {"query": "string，可选"}),
        _tool("read_scene_record", "读取本人物亲历过的一次完整冻结记录。", {"scene_id": "string"}),
        _tool("list_todos", "列出本人物尚未完成的待办。", {}),
    ]
    if phase == "settlement":
        tools.extend(
            [
                _tool(
                    "record_knowledge",
                    "把本场景中新获得、推断或听说的一项信息写入动态认知，并保留来源与置信度。",
                    {
                        "claim": "string",
                        "source_type": "transcript|document|observation|hearsay|inference",
                        "source_id": "turn_id|document_id|null",
                        "confidence": "low|medium|high",
                        "related_actor_ids": ["actor_id"],
                        "related_issue_ids": ["issue_id"],
                    },
                ),
                _tool(
                    "record_memory",
                    "把本次亲历形成的私人记忆写入自己的记忆库。",
                    {
                        "summary": "string",
                        "memory_type": "episodic|semantic|relationship",
                        "importance": "1-5",
                        "related_actor_ids": ["actor_id"],
                        "related_issue_ids": ["issue_id"],
                        "source_turn_ids": ["turn_id"],
                    },
                ),
                _tool(
                    "record_todo",
                    "记录本人准备跟进的待办，不自动取得正式决策效力。",
                    {
                        "summary": "string",
                        "due_date": "YYYY-MM-DD|null",
                        "priority": "low|normal|high|urgent",
                        "requires_formal_decision": "boolean",
                        "related_actor_ids": ["actor_id"],
                        "related_issue_ids": ["issue_id"],
                    },
                ),
                _tool(
                    "record_relationship_impression",
                    "记录本人物对一名亲历对象的工作关系印象变化；只改变本人物的主观看法。",
                    {
                        "target_id": "player或actor_id",
                        "signal": "improved|unchanged|strained",
                        "note": "string",
                        "related_issue_id": "issue_id|null",
                    },
                ),
                _tool(
                    "record_commitment",
                    "记录本场景中实际形成的交办、承诺或条件交换及其正式效力边界。",
                    {
                        "commitment_type": "instruction|promise|conditional_exchange|reporting_duty",
                        "giver_id": "player或actor_id",
                        "receiver_id": "player或actor_id",
                        "summary": "string",
                        "condition": "string|null",
                        "due_date": "YYYY-MM-DD|null",
                        "visibility": "private|participants|internal|public",
                        "requires_formal_decision": "boolean",
                    },
                ),
                _tool("contact_actor", "申请会后联系一名认识的人；只展开一跳。", {"target_id": "actor_id", "summary": "string"}),
                _tool("request_information", "申请向认识的人或机构核实信息。", {"target_id": "actor_id", "title": "string|null", "summary": "string"}),
                _tool(
                    "propose_action",
                    "提出权限内准备或需要正式决定的行动意图。",
                    {
                        "summary": "string",
                        "action_type": "string",
                        "target_ids": ["actor_id"],
                        "due_date": "YYYY-MM-DD|null",
                        "requires_formal_decision": "boolean",
                    },
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
            query = str(call.arguments.get("query", "")).strip()
            contacts = _known_people(game, actor_id)
            if query:
                contacts = [item for item in contacts if query in " ".join(str(value) for value in item.values())]
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
            query = str(call.arguments.get("query", "")).strip()
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
            scene_id = str(call.arguments.get("scene_id", ""))
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


def _tool(name: str, description: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, "description": description, "arguments": arguments}


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


def _find_visible_document(
    game: StoredGame,
    actor_id: str,
    document_id: str,
    staged_effects: Sequence[AgentToolEffect],
) -> Dict[str, Any]:
    document = next(
        (item for item in _visible_documents(game, actor_id, staged_effects) if item["id"] == document_id),
        None,
    )
    if document is None:
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
