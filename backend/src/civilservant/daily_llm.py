from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Type, TypeVar

import httpx

from .config import PROMPT_DIR
from pydantic import BaseModel, ValidationError

from .daily_agent_tools import agent_tool_catalog, execute_agent_tool
from .daily_engine import actor_agent_projection, actor_available_knowledge_ids
from .daily_models import (
    AgentToolCall,
    AgentToolEffect,
    AgentUtterance,
    PostSceneResult,
    SpeechIntent,
    SuperiorReaction,
)
from .llm import LlmError, validate_api_base
from .models import StoredGame


class DailyAgentProvider:
    def __init__(self, timeout_seconds: float = 35.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.system_prompt = _read_prompt(PROMPT_DIR / "daily_actor.md")

    def resolve_conversation(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
        player_message: str,
    ) -> AgentUtterance:
        result = self._run_agent_loop(
            api_key=api_key,
            game=game,
            actor_id=actor_id,
            phase="interaction",
            task="conversation_reply",
            instruction=(
                "以当前人物身份直接回应玩家。需要核对材料、过去记录或联系人时先调用工具；"
                "可以在权限内形成或修改自己的游戏内工作草稿。"
            ),
            task_input={"player_message": player_message},
            final_schema={
                "text": "string",
                "used_belief_ids": ["knowledge_id|reference_material_id|document_id"],
            },
            output_model=AgentUtterance,
            max_tokens=1000,
        )
        self._validate_beliefs(game, actor_id, result)
        return result

    def resolve_meeting_utterance(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> AgentUtterance:
        result = self._run_agent_loop(
            api_key=api_key,
            game=game,
            actor_id=actor_id,
            phase="interaction",
            task="meeting_utterance",
            instruction=(
                "你已经获得发言权。结合当前会议记录作一段简洁、有职务立场的发言。"
                "如果需要核对文件或本人记录，必须先调用相应工具。"
            ),
            task_input={},
            final_schema={
                "text": "string",
                "used_belief_ids": ["knowledge_id|reference_material_id|document_id"],
            },
            output_model=AgentUtterance,
            max_tokens=1100,
        )
        self._validate_beliefs(game, actor_id, result)
        return result

    def resolve_speech_intent(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> SpeechIntent:
        payload = {
            "task": "speech_intent",
            "instruction": (
                "只判断此刻是否希望发言。考虑自己是否有新信息、是否需要回应、职务责任、"
                "刚刚是否已经发言以及沉默是否更符合人物利益。不要生成完整发言。"
            ),
            "context": actor_agent_projection(game, actor_id),
            "output_schema": {
                "wants_to_speak": "boolean",
                "responds_to_turn_id": "string|null",
                "intent": "short string",
                "urgency": "low|normal|high",
            },
        }
        return SpeechIntent.model_validate(self._request(api_key, game, payload, 240))

    def resolve_post_scene(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> PostSceneResult:
        result = self._run_agent_loop(
            api_key=api_key,
            game=game,
            actor_id=actor_id,
            phase="settlement",
            task="post_scene_settlement",
            instruction=(
                "场景即将冻结。只从当前人物的职责、认知和亲历出发，形成一条私人记忆，"
                "并使用 record_memory 写入；需要跟进的事项使用 record_todo。"
                "场景中新获得的事实、传闻或推断使用 record_knowledge 保存来源和置信度；"
                "对具体人物的工作关系判断有变化时使用 record_relationship_impression。"
                "交办、承诺或条件交换必须使用 record_commitment；读写文件、联络、核查和行动使用对应工具。"
                "工具操作只是待提交申请，不能自行改变世界事实。需要会议或正式程序的行动必须标记。"
            ),
            task_input={},
            final_schema={
                "memory": "string",
                "relationship_signal": "improved|unchanged|strained",
                "intents": [
                    {
                        "kind": "contact_actor|draft_document|request_information|propose_action|none",
                        "summary": "string",
                        "target_id": "actor_id|null",
                        "title": "string|null",
                        "action_type": "string|null",
                        "requires_formal_decision": "boolean",
                    }
                ],
            },
            output_model=PostSceneResult,
            max_tokens=850,
        )
        if not any(effect.kind == "record_memory" for effect in result.tool_effects):
            scene = game.state.get("active_scene")
            fallback = AgentToolEffect(
                kind="record_memory",
                payload={
                    "summary": result.memory,
                    "memory_type": "episodic",
                    "importance": 3,
                    "related_actor_ids": [
                        item["actor_id"]
                        for item in scene.get("participants", [])
                        if item["actor_id"] != actor_id
                    ] if scene else [],
                    "related_issue_ids": [],
                    "source_turn_ids": [item["id"] for item in scene.get("transcript", [])[-12:]] if scene else [],
                },
            )
            result = result.model_copy(update={"tool_effects": result.tool_effects + [fallback]})
        return result

    def _run_agent_loop(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
        phase: str,
        task: str,
        instruction: str,
        task_input: Dict[str, Any],
        final_schema: Dict[str, Any],
        output_model: Type["AgentOutputT"],
        max_tokens: int,
    ) -> "AgentOutputT":
        staged_effects: List[AgentToolEffect] = []
        tool_results: List[Dict[str, Any]] = []
        for loop_index in range(128):
            payload = {
                "task": task,
                "instruction": instruction,
                "context": actor_agent_projection(game, actor_id),
                "task_input": task_input,
                "available_tools": agent_tool_catalog(phase),
                "tool_results": tool_results,
                "response_protocol": {
                    "tool_calls": [
                        {"call_id": "unique string", "name": "available tool name", "arguments": {}}
                    ],
                    "final": final_schema,
                    "rule": (
                        "需要工具时返回非空tool_calls且final为null；看完工具结果后继续。"
                        "完成时tool_calls必须为空并把最终答案放入final。"
                    ),
                },
                "loop_index": loop_index,
            }
            data = self._request(api_key, game, payload, max_tokens)
            raw_calls = data.get("tool_calls", [])
            if raw_calls:
                if not isinstance(raw_calls, list):
                    raise LlmError("人物 Agent 工具调用结构错误。")
                for raw_call in raw_calls:
                    try:
                        call = AgentToolCall.model_validate(raw_call)
                    except ValidationError as exc:
                        raise LlmError("人物 Agent 返回了无效工具参数。") from exc
                    tool_result, effect = execute_agent_tool(
                        game,
                        actor_id,
                        phase,
                        call,
                        staged_effects,
                    )
                    tool_results.append(tool_result)
                    if effect is not None:
                        staged_effects.append(effect)
                continue
            final_data = data.get("final", data)
            if not isinstance(final_data, dict):
                raise LlmError("人物 Agent 没有返回最终结构化结果。")
            try:
                result = output_model.model_validate(final_data)
            except ValidationError as exc:
                raise LlmError("人物 Agent 最终输出不符合结构约束。") from exc
            if hasattr(result, "tool_effects"):
                result = result.model_copy(update={"tool_effects": staged_effects})
            return result
        raise LlmError("人物 Agent 在工具循环上限内没有形成最终答复。")

    def resolve_superior_reaction(
        self,
        *,
        api_key: str,
        game: StoredGame,
        document_id: str,
        cover_note: str,
    ) -> SuperiorReaction:
        document = next(
            (item for item in game.state["documents"] if item["id"] == document_id),
            None,
        )
        if document is None:
            raise LlmError("待报送文件不存在。")
        payload = {
            "task": "superior_document_reaction",
            "instruction": (
                "你即将收到下级报送材料。依据上级角色的职责、既有认知和材料本身，"
                "决定立即回复、设置后续反馈、延迟处理或暂不行动。不得假定材料之外的事实。"
            ),
            "context": actor_agent_projection(game, "superior"),
            "submission": {
                "title": document["title"],
                "summary": document["summary"],
                "content": document["content"],
                "annotations": document["annotations"],
                "source_document_ids": document["source_document_ids"],
                "cover_note": cover_note,
            },
            "output_schema": {
                "immediate_reply": "string",
                "reaction_kind": "immediate|conditional_follow_up|delayed|none",
                "condition": "string|null",
                "delay_days": "integer|null",
                "expires_after_days": "integer|null",
                "proposed_action": "string|null",
            },
        }
        return SuperiorReaction.model_validate(self._request(api_key, game, payload, 600))

    def _request(
        self,
        api_key: str,
        game: StoredGame,
        payload: Dict[str, Any],
        max_tokens: int,
    ) -> Dict[str, Any]:
        base = validate_api_base(game.api_base)
        body = {
            "model": game.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.42,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            response = httpx.post(
                "{}/chat/completions".format(base),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LlmError("人物 Agent 响应超时，任何场景状态都没有被部分提交。") from exc
        except httpx.HTTPError as exc:
            raise LlmError("无法连接 DeepSeek，人物输出尚未提交。") from exc
        if response.status_code == 401:
            raise LlmError("API Key 已失效，请重新输入。")
        if response.status_code >= 400:
            raise LlmError("DeepSeek 返回错误（HTTP {}）。".format(response.status_code))
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError("人物 Agent 没有返回可用的结构化 JSON。") from exc
        if not isinstance(data, dict):
            raise LlmError("人物 Agent 返回结构错误。")
        return data

    @staticmethod
    def _validate_beliefs(game: StoredGame, actor_id: str, result: AgentUtterance) -> None:
        if not set(result.used_belief_ids).issubset(set(actor_available_knowledge_ids(game, actor_id))):
            raise LlmError("人物 Agent 引用了其认知范围外的信息，输出已拒绝。")


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


AgentOutputT = TypeVar("AgentOutputT", bound=BaseModel)
