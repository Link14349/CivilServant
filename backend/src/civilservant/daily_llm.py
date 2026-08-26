from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

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


FINAL_TOOL_NAME = "submit_final_result"


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
            max_tokens=12000,
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
            max_tokens=12000,
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
            max_tokens=12000,
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
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "instruction": instruction,
                        "context": actor_agent_projection(game, actor_id),
                        "task_input": task_input,
                        "final_result_description": final_schema,
                        "agent_loop": {
                            "maximum_rounds": 128,
                            "rule": (
                                "需要资料或行动时调用相应原生工具；每轮工具结果返回后继续。"
                                "完成时必须单独调用 submit_final_result，不要在普通文本中伪造工具调用或最终 JSON。"
                            ),
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        tools = agent_tool_catalog(phase) + [_final_tool(output_model)]
        for loop_index in range(128):
            choice = self._request_native_tool_turn(
                api_key=api_key,
                game=game,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                loop_index=loop_index,
            )
            message = choice.get("message")
            if not isinstance(message, dict):
                raise LlmError("DeepSeek 人物响应缺少 message。")
            raw_calls = message.get("tool_calls")
            if not isinstance(raw_calls, list) or not raw_calls:
                finish_reason = str(choice.get("finish_reason") or "unknown")
                raise LlmError(
                    "人物 Agent 没有调用工具或提交最终结果（finish_reason={}）。".format(
                        finish_reason
                    )
                )
            assistant_message: Dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": raw_calls,
            }
            reasoning_content = message.get("reasoning_content")
            if isinstance(reasoning_content, str):
                assistant_message["reasoning_content"] = reasoning_content
            messages.append(assistant_message)

            contains_final = any(
                isinstance(raw_call, dict)
                and isinstance(raw_call.get("function"), dict)
                and raw_call["function"].get("name") == FINAL_TOOL_NAME
                for raw_call in raw_calls
            )
            for raw_call in raw_calls:
                call_id, name, arguments, parse_error = _parse_native_tool_call(raw_call)
                if parse_error:
                    messages.append(_tool_message(call_id, {"ok": False, "error": parse_error}))
                    continue
                if name == FINAL_TOOL_NAME:
                    if len(raw_calls) != 1:
                        messages.append(
                            _tool_message(
                                call_id,
                                {
                                    "ok": False,
                                    "error": "submit_final_result 必须单独调用，不能与其他工具并行。",
                                },
                            )
                        )
                        continue
                    try:
                        result = output_model.model_validate(arguments)
                    except ValidationError as exc:
                        messages.append(
                            _tool_message(
                                call_id,
                                {
                                    "ok": False,
                                    "error": "最终结果不符合结构约束：{}".format(exc),
                                },
                            )
                        )
                        continue
                    if hasattr(result, "tool_effects"):
                        result = result.model_copy(update={"tool_effects": staged_effects})
                    return result
                if contains_final:
                    messages.append(
                        _tool_message(
                            call_id,
                            {
                                "ok": False,
                                "error": "本轮同时提交了最终结果；其他工具没有执行，请下一轮重新调用。",
                            },
                        )
                    )
                    continue
                try:
                    call = AgentToolCall.model_validate(
                        {"call_id": call_id, "name": name, "arguments": arguments}
                    )
                except ValidationError as exc:
                    messages.append(
                        _tool_message(
                            call_id,
                            {"ok": False, "error": "工具名称或参数入口无效：{}".format(exc)},
                        )
                    )
                    continue
                tool_result, effect = execute_agent_tool(
                    game,
                    actor_id,
                    phase,
                    call,
                    staged_effects,
                )
                messages.append(_tool_message(call_id, tool_result))
                if effect is not None:
                    staged_effects.append(effect)
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
        response_data = self._post_chat(api_key, game, body)
        choice = _first_choice(response_data)
        _raise_for_incomplete_finish(choice, "结构化输出")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise LlmError("DeepSeek 结构化响应缺少 message。")
        content = message.get("content")
        if not isinstance(content, str):
            raise LlmError(
                "人物 Agent 没有返回结构化正文（finish_reason={}）。".format(
                    choice.get("finish_reason") or "unknown"
                )
            )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmError(
                "人物 Agent 的结构化正文不是合法 JSON"
                "（finish_reason={}，content_length={}，error_position={}）。".format(
                    choice.get("finish_reason") or "unknown",
                    len(content),
                    exc.pos,
                )
            ) from exc
        if not isinstance(data, dict):
            raise LlmError("人物 Agent 返回结构错误。")
        return data

    def _request_native_tool_turn(
        self,
        *,
        api_key: str,
        game: StoredGame,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int,
        loop_index: int,
    ) -> Dict[str, Any]:
        body = {
            "model": game.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "required",
            "thinking": {"type": "disabled"},
            "temperature": 0.42,
            "max_tokens": max_tokens,
            "stream": False,
        }
        response_data = self._post_chat(api_key, game, body)
        choice = _first_choice(response_data)
        _raise_for_incomplete_finish(choice, "第 {} 轮工具调用".format(loop_index + 1))
        return choice

    def _post_chat(
        self,
        api_key: str,
        game: StoredGame,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = validate_api_base(game.api_base)
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
            response_data = response.json()
        except ValueError as exc:
            raise LlmError("DeepSeek HTTP 响应不是合法 JSON。") from exc
        if not isinstance(response_data, dict):
            raise LlmError("DeepSeek HTTP 响应结构错误。")
        return response_data

    @staticmethod
    def _validate_beliefs(game: StoredGame, actor_id: str, result: AgentUtterance) -> None:
        if not set(result.used_belief_ids).issubset(set(actor_available_knowledge_ids(game, actor_id))):
            raise LlmError("人物 Agent 引用了其认知范围外的信息，输出已拒绝。")


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _final_tool(output_model: Type[BaseModel]) -> Dict[str, Any]:
    schema = output_model.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("tool_effects", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [item for item in required if item != "tool_effects"]
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        definitions.pop("AgentToolEffect", None)
    return {
        "type": "function",
        "function": {
            "name": FINAL_TOOL_NAME,
            "description": (
                "结束本次人物 Agent Loop 并提交最终结构化结果。"
                "必须在所需读取、记录和行动工具完成后单独调用。"
            ),
            "parameters": schema,
        },
    }


def _first_choice(response_data: Dict[str, Any]) -> Dict[str, Any]:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LlmError("DeepSeek 响应缺少有效 choice。")
    return choices[0]


def _raise_for_incomplete_finish(choice: Dict[str, Any], stage: str) -> None:
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        raise LlmError("人物 Agent {}达到输出上限并被截断，任何暂存操作均未提交。".format(stage))
    if finish_reason == "content_filter":
        raise LlmError("人物 Agent {}被内容过滤器中止，任何暂存操作均未提交。".format(stage))
    if finish_reason == "insufficient_system_resource":
        raise LlmError("人物 Agent {}因模型服务资源不足而中止，可以重试。".format(stage))
    if finish_reason not in {"stop", "tool_calls"}:
        raise LlmError(
            "人物 Agent {}以未知原因结束（finish_reason={}）。".format(
                stage,
                finish_reason or "missing",
            )
        )


def _parse_native_tool_call(
    raw_call: Any,
) -> Tuple[str, str, Dict[str, Any], Optional[str]]:
    if not isinstance(raw_call, dict):
        return "invalid-tool-call", "", {}, "原生 tool_call 不是对象。"
    call_id = str(raw_call.get("id") or "invalid-tool-call")
    function = raw_call.get("function")
    if raw_call.get("type") != "function" or not isinstance(function, dict):
        return call_id, "", {}, "原生 tool_call 缺少 function。"
    name = str(function.get("name") or "")
    raw_arguments = function.get("arguments")
    if isinstance(raw_arguments, dict):
        arguments = raw_arguments
    elif isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return (
                call_id,
                name,
                {},
                "工具参数不是合法 JSON（content_length={}，error_position={}）。".format(
                    len(raw_arguments),
                    exc.pos,
                ),
            )
    else:
        return call_id, name, {}, "原生 tool_call 的 arguments 不是字符串或对象。"
    if not isinstance(arguments, dict):
        return call_id, name, {}, "工具参数必须是 JSON 对象。"
    if not name:
        return call_id, name, arguments, "原生 tool_call 缺少工具名称。"
    return call_id, name, arguments, None


def _tool_message(call_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(payload, ensure_ascii=False),
    }


AgentOutputT = TypeVar("AgentOutputT", bound=BaseModel)
