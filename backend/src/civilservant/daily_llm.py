from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

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
MAX_AGENT_LOOP_ROUNDS = 128
PREFERRED_AGENT_LOOP_ROUNDS = 32
MAX_FINAL_REPAIR_ATTEMPTS = 3
MAX_CONSECUTIVE_TOOL_FAILURES = 3


class AgentGenerationCanceled(RuntimeError):
    pass


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
        on_text_update: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_trace: Optional[Callable[[Dict[str, Any]], None]] = None,
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
            on_text_update=on_text_update,
            on_status=on_status,
            is_cancelled=is_cancelled,
            on_trace=on_trace,
        )
        self._validate_beliefs(game, actor_id, result)
        return result

    def resolve_meeting_utterance(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
        on_text_update: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_trace: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentUtterance:
        result = self._run_agent_loop(
            api_key=api_key,
            game=game,
            actor_id=actor_id,
            phase="interaction",
            task="meeting_utterance",
            instruction=(
                "你已经获得发言权。结合当前会议记录与本人已知信息作一段简洁、有职务立场的发言。"
                "会议记录、参会人员、联系人名单、可见文件与本人记忆都已包含在上下文中，不要重复检索。"
                "只有当你确实需要核对某份文件的正文，或确认某位与会者的具体职务关系时，才调用相应工具；"
                "信息足够时立即调用 submit_final_result 提交发言，不要无谓地反复调用 list_contacts 等检索工具。"
            ),
            task_input={},
            final_schema={
                "text": "string",
                "used_belief_ids": ["knowledge_id|reference_material_id|document_id"],
            },
            output_model=AgentUtterance,
            max_tokens=12000,
            on_text_update=on_text_update,
            on_status=on_status,
            is_cancelled=is_cancelled,
            on_trace=on_trace,
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
        on_trace: Optional[Callable[[Dict[str, Any]], None]] = None,
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
            on_trace=on_trace,
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
        on_text_update: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_trace: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "AgentOutputT":
        staged_effects: List[AgentToolEffect] = []
        seen_tool_calls: Dict[str, int] = {}
        consecutive_tool_failures = 0
        final_repair_attempts = 0
        force_final = False
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
                            "preferred_completion_rounds": PREFERRED_AGENT_LOOP_ROUNDS,
                            "maximum_rounds": MAX_AGENT_LOOP_ROUNDS,
                            "rule": (
                                "128 轮是不可突破的硬上限，不是应当用满的额度；"
                                "把 32 轮以内完成作为强目标。先判断真正需要的信息和操作，"
                                "避免重复调用同一工具、反复读取同一材料或查询无关内容；"
                                "已有信息足够时立即停止调用其他工具。需要资料或行动时调用相应原生工具；"
                                "每轮工具结果返回后继续。"
                                "完成时必须单独调用 submit_final_result，不要在普通文本中伪造工具调用或最终 JSON。"
                            ),
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        tools = agent_tool_catalog(phase) + [_final_tool(output_model)]
        _emit_trace(
            on_trace,
            {
                "kind": "agent_start",
                "round": 0,
                "title": "开始人物 Agent Loop",
                "payload": {
                    "actor_id": actor_id,
                    "phase": phase,
                    "task": task,
                    "instruction": instruction,
                    "task_input": task_input,
                    "tool_names": [item["function"]["name"] for item in tools],
                    "preferred_completion_rounds": PREFERRED_AGENT_LOOP_ROUNDS,
                    "maximum_rounds": MAX_AGENT_LOOP_ROUNDS,
                },
            },
        )
        for loop_index in range(MAX_AGENT_LOOP_ROUNDS):
            _check_cancelled(is_cancelled)
            round_number = loop_index + 1
            if round_number >= PREFERRED_AGENT_LOOP_ROUNDS:
                force_final = True
            tool_choice: Any = (
                {"type": "function", "function": {"name": FINAL_TOOL_NAME}}
                if force_final
                else "required"
            )
            if on_status:
                on_status("正在组织第 {} 轮判断…".format(round_number))
            _emit_trace(
                on_trace,
                {
                    "kind": "model_request",
                    "round": round_number,
                    "title": "请求模型选择下一步",
                    "payload": {
                        "tool_choice": tool_choice,
                        "message_count": len(messages),
                        "staged_effect_count": len(staged_effects),
                    },
                },
            )
            choice = self._request_native_tool_turn(
                api_key=api_key,
                game=game,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                loop_index=loop_index,
                tool_choice=tool_choice,
                on_text_update=on_text_update,
                is_cancelled=is_cancelled,
            )
            message = choice.get("message")
            if not isinstance(message, dict):
                raise LlmError("DeepSeek 人物响应缺少 message。")
            raw_calls = message.get("tool_calls")
            if not isinstance(raw_calls, list) or not raw_calls:
                finish_reason = str(choice.get("finish_reason") or "unknown")
                _emit_trace(
                    on_trace,
                    {
                        "kind": "protocol_error",
                        "round": round_number,
                        "title": "模型没有调用任何工具",
                        "payload": {
                            "finish_reason": finish_reason,
                            "content": message.get("content"),
                        },
                    },
                )
                final_repair_attempts += 1
                if final_repair_attempts >= MAX_FINAL_REPAIR_ATTEMPTS:
                    return _fallback_agent_output(
                        output_model,
                        staged_effects,
                        task,
                        on_text_update,
                        on_status,
                        on_trace,
                        "模型连续没有调用终止工具。",
                    )
                messages.append({"role": "assistant", "content": message.get("content") or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": "协议修复：现在只能单独调用 submit_final_result，不要再输出普通正文。",
                    }
                )
                force_final = True
                continue
            _emit_trace(
                on_trace,
                {
                    "kind": "model_response",
                    "round": round_number,
                    "title": "模型返回工具调用",
                    "payload": {
                        "finish_reason": choice.get("finish_reason"),
                        "content": message.get("content"),
                        "tool_calls": raw_calls,
                    },
                },
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
                _emit_trace(
                    on_trace,
                    {
                        "kind": "tool_call",
                        "round": round_number,
                        "title": "调用 {}".format(name or "未知工具"),
                        "payload": {
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                            "parse_error": parse_error,
                        },
                    },
                )
                if parse_error:
                    tool_result = {"ok": False, "error": parse_error}
                    messages.append(_tool_message(call_id, tool_result))
                    consecutive_tool_failures += 1
                    _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                    if consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES:
                        return _fallback_agent_output(
                            output_model,
                            staged_effects,
                            task,
                            on_text_update,
                            on_status,
                            on_trace,
                            "模型连续返回无法解析的工具调用。",
                        )
                    continue
                if name == FINAL_TOOL_NAME:
                    if len(raw_calls) != 1:
                        tool_result = {
                            "ok": False,
                            "error": "submit_final_result 必须单独调用，不能与其他工具并行。",
                        }
                        messages.append(_tool_message(call_id, tool_result))
                        final_repair_attempts += 1
                        force_final = True
                        _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                        if final_repair_attempts >= MAX_FINAL_REPAIR_ATTEMPTS:
                            return _fallback_agent_output(
                                output_model,
                                staged_effects,
                                task,
                                on_text_update,
                                on_status,
                                on_trace,
                                "模型连续把终止工具与其他工具混合调用。",
                            )
                        continue
                    try:
                        result = output_model.model_validate(arguments)
                    except ValidationError as exc:
                        tool_result = {
                            "ok": False,
                            "error": "最终结果不符合结构约束：{}".format(exc),
                        }
                        messages.append(_tool_message(call_id, tool_result))
                        final_repair_attempts += 1
                        force_final = True
                        _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                        if final_repair_attempts >= MAX_FINAL_REPAIR_ATTEMPTS:
                            return _fallback_agent_output(
                                output_model,
                                staged_effects,
                                task,
                                on_text_update,
                                on_status,
                                on_trace,
                                "终止工具连续返回无效参数。",
                            )
                        continue
                    if hasattr(result, "tool_effects"):
                        result = result.model_copy(update={"tool_effects": staged_effects})
                    if on_text_update and isinstance(result, AgentUtterance):
                        on_text_update(result.text)
                    if on_status:
                        on_status("发言生成完成，正在写入会议记录…")
                    _emit_trace(
                        on_trace,
                        {
                            "kind": "agent_complete",
                            "round": round_number,
                            "title": "人物 Agent 已提交最终结果",
                            "payload": {
                                "result": result.model_dump(mode="json"),
                                "staged_effect_count": len(staged_effects),
                            },
                        },
                    )
                    return result
                if contains_final:
                    tool_result = {
                        "ok": False,
                        "error": "本轮同时提交了最终结果；其他工具没有执行，请下一轮重新调用。",
                    }
                    messages.append(_tool_message(call_id, tool_result))
                    force_final = True
                    _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                    continue
                if force_final:
                    tool_result = {
                        "ok": False,
                        "error": "Harness 已进入收敛阶段，现在只能调用 submit_final_result。",
                    }
                    messages.append(_tool_message(call_id, tool_result))
                    final_repair_attempts += 1
                    _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                    if final_repair_attempts >= MAX_FINAL_REPAIR_ATTEMPTS:
                        return _fallback_agent_output(
                            output_model,
                            staged_effects,
                            task,
                            on_text_update,
                            on_status,
                            on_trace,
                            "模型在强制收敛阶段仍未调用终止工具。",
                        )
                    continue
                signature = _tool_signature(name, arguments)
                if signature in seen_tool_calls:
                    seen_tool_calls[signature] += 1
                    tool_result = {
                        "ok": False,
                        "error": (
                            "完全相同的工具调用已经执行过，结果已在上文。"
                            "不要重复调用；请使用已有结果并提交最终答复。"
                        ),
                        "duplicate_count": seen_tool_calls[signature],
                    }
                    messages.append(_tool_message(call_id, tool_result))
                    force_final = True
                    _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                    _emit_trace(
                        on_trace,
                        {
                            "kind": "convergence_guard",
                            "round": round_number,
                            "title": "检测到重复工具调用，下一轮强制结束",
                            "payload": {"signature": signature},
                        },
                    )
                    continue
                seen_tool_calls[signature] = 1
                try:
                    call = AgentToolCall.model_validate(
                        {"call_id": call_id, "name": name, "arguments": arguments}
                    )
                except ValidationError as exc:
                    tool_result = {"ok": False, "error": "工具名称或参数入口无效：{}".format(exc)}
                    messages.append(_tool_message(call_id, tool_result))
                    consecutive_tool_failures += 1
                    _emit_tool_result(on_trace, round_number, call_id, name, tool_result)
                    if consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES:
                        return _fallback_agent_output(
                            output_model,
                            staged_effects,
                            task,
                            on_text_update,
                            on_status,
                            on_trace,
                            "模型连续调用不存在的工具或提供无效入口参数。",
                        )
                    continue
                if on_status:
                    on_status(_tool_status(call.name))
                tool_result, effect = execute_agent_tool(
                    game,
                    actor_id,
                    phase,
                    call,
                    staged_effects,
                )
                messages.append(_tool_message(call_id, tool_result))
                _emit_tool_result(on_trace, round_number, call_id, call.name, tool_result)
                if effect is not None:
                    staged_effects.append(effect)
                if tool_result.get("ok"):
                    consecutive_tool_failures = 0
                else:
                    consecutive_tool_failures += 1
                    if consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES:
                        force_final = True
            if round_number >= PREFERRED_AGENT_LOOP_ROUNDS - 1:
                force_final = True
                _emit_trace(
                    on_trace,
                    {
                        "kind": "convergence_guard",
                        "round": round_number,
                        "title": "达到首选轮数，下一轮强制提交最终结果",
                        "payload": {"preferred_completion_rounds": PREFERRED_AGENT_LOOP_ROUNDS},
                    },
                )
        return _fallback_agent_output(
            output_model,
            staged_effects,
            task,
            on_text_update,
            on_status,
            on_trace,
            "达到 128 轮硬上限仍未形成有效终止调用。",
        )

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
        tool_choice: Any,
        on_text_update: Optional[Callable[[str], None]],
        is_cancelled: Optional[Callable[[], bool]],
    ) -> Dict[str, Any]:
        body = {
            "model": game.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "thinking": {"type": "disabled"},
            "temperature": 0.42,
            "max_tokens": max_tokens,
            "stream": on_text_update is not None,
        }
        if on_text_update is None:
            response_data = self._post_chat(api_key, game, body)
        else:
            response_data = self._post_chat_stream(
                api_key,
                game,
                body,
                on_text_update=on_text_update,
                is_cancelled=is_cancelled,
            )
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

    def _post_chat_stream(
        self,
        api_key: str,
        game: StoredGame,
        body: Dict[str, Any],
        *,
        on_text_update: Callable[[str], None],
        is_cancelled: Optional[Callable[[], bool]],
    ) -> Dict[str, Any]:
        base = validate_api_base(game.api_base)
        content_parts: List[str] = []
        tool_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        try:
            with httpx.stream(
                "POST",
                "{}/chat/completions".format(base),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code == 401:
                    raise LlmError("API Key 已失效，请重新输入。")
                if response.status_code >= 400:
                    raise LlmError("DeepSeek 返回错误（HTTP {}）。".format(response.status_code))
                for line in response.iter_lines():
                    _check_cancelled(is_cancelled)
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise LlmError("DeepSeek 流式事件不是合法 JSON。") from exc
                    choices = chunk.get("choices") if isinstance(chunk, dict) else None
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        continue
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, str):
                        content_parts.append(content)
                    raw_tool_deltas = delta.get("tool_calls")
                    if not isinstance(raw_tool_deltas, list):
                        continue
                    for raw_delta in raw_tool_deltas:
                        if not isinstance(raw_delta, dict):
                            continue
                        index = int(raw_delta.get("index", 0))
                        accumulated = tool_calls.setdefault(
                            index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if isinstance(raw_delta.get("id"), str):
                            accumulated["id"] += raw_delta["id"]
                        if isinstance(raw_delta.get("type"), str):
                            accumulated["type"] = raw_delta["type"]
                        function_delta = raw_delta.get("function")
                        if not isinstance(function_delta, dict):
                            continue
                        if isinstance(function_delta.get("name"), str):
                            accumulated["function"]["name"] += function_delta["name"]
                        if isinstance(function_delta.get("arguments"), str):
                            accumulated["function"]["arguments"] += function_delta["arguments"]
                        if accumulated["function"]["name"] == FINAL_TOOL_NAME:
                            partial_text = _extract_partial_json_string_field(
                                accumulated["function"]["arguments"],
                                "text",
                            )
                            if partial_text is not None:
                                on_text_update(partial_text)
        except AgentGenerationCanceled:
            raise
        except httpx.TimeoutException as exc:
            raise LlmError("人物 Agent 流式响应超时，任何场景状态都没有被部分提交。") from exc
        except httpx.HTTPError as exc:
            raise LlmError("无法连接 DeepSeek，人物流式输出尚未提交。") from exc
        if finish_reason is None:
            raise LlmError("DeepSeek 流式响应在给出 finish_reason 前中断，任何暂存操作均未提交。")
        return {
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts) or None,
                        "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
                    },
                }
            ]
        }

    @staticmethod
    def _validate_beliefs(game: StoredGame, actor_id: str, result: AgentUtterance) -> None:
        allowed = set(actor_available_knowledge_ids(game, actor_id))
        offending = sorted(set(result.used_belief_ids) - allowed)
        if offending:
            raise LlmError(
                "人物 Agent 引用了其认知范围外的信息，输出已拒绝"
                "（越界引用：{}）。".format("、".join(offending))
            )


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


def _tool_signature(name: str, arguments: Dict[str, Any]) -> str:
    return "{}:{}".format(
        name,
        json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _emit_trace(
    on_trace: Optional[Callable[[Dict[str, Any]], None]],
    event: Dict[str, Any],
) -> None:
    if on_trace:
        on_trace(event)


def _emit_tool_result(
    on_trace: Optional[Callable[[Dict[str, Any]], None]],
    round_number: int,
    call_id: str,
    name: str,
    result: Dict[str, Any],
) -> None:
    _emit_trace(
        on_trace,
        {
            "kind": "tool_result",
            "round": round_number,
            "title": "{} 返回{}".format(name or "未知工具", "成功" if result.get("ok") else "错误"),
            "payload": {"call_id": call_id, "name": name, "result": result},
        },
    )


def _fallback_agent_output(
    output_model: Type[BaseModel],
    staged_effects: List[AgentToolEffect],
    task: str,
    on_text_update: Optional[Callable[[str], None]],
    on_status: Optional[Callable[[str], None]],
    on_trace: Optional[Callable[[Dict[str, Any]], None]],
    reason: str,
) -> Any:
    # 收敛失败时保留已 staged 的写工具效果，避免模型跑完后已形成的记忆/待办/认知被整体丢弃。
    # 结果模型的 tool_effects 有 max_length=8 上限，超出部分只能舍弃，优先保留先写入的。
    preserved = staged_effects[:8]
    if output_model is AgentUtterance:
        result: BaseModel = AgentUtterance(
            text="这件事我还需要进一步核实，暂时不能给出可靠答复。",
            used_belief_ids=[],
            tool_effects=preserved,
        )
        if on_text_update:
            on_text_update(result.text)  # type: ignore[attr-defined]
    elif output_model is PostSceneResult:
        result = PostSceneResult(
            memory="本次场景已经结束，但暂未形成足够可靠的新增判断。",
            relationship_signal="unchanged",
            intents=[],
            tool_effects=preserved,
        )
    else:
        raise LlmError("人物 Agent 未能收敛：{}".format(reason))
    if on_status:
        on_status("人物 Agent 未按协议收敛，已使用安全降级答复。")
    _emit_trace(
        on_trace,
        {
            "kind": "safe_fallback",
            "round": 0,
            "title": "Agent 未收敛，使用安全降级结果",
            "payload": {
                "task": task,
                "reason": reason,
                "preserved_staged_effect_count": len(preserved),
                "discarded_staged_effect_count": len(staged_effects) - len(preserved),
                "result": result.model_dump(mode="json"),
            },
        },
    )
    return result


def _check_cancelled(is_cancelled: Optional[Callable[[], bool]]) -> None:
    if is_cancelled and is_cancelled():
        raise AgentGenerationCanceled("人物发言已被玩家打断。")


def _tool_status(tool_name: str) -> str:
    return {
        "list_contacts": "正在核对联系人…",
        "list_visible_files": "正在查找有权查看的文件…",
        "read_file": "正在查阅文件正文…",
        "write_file": "正在起草工作材料…",
        "revise_file": "正在修改工作材料…",
        "list_memories": "正在回想既往谈话…",
        "list_scene_records": "正在检索亲历记录…",
        "read_scene_record": "正在回看完整谈话记录…",
        "list_todos": "正在核对待办事项…",
    }.get(tool_name, "正在处理人物自己的工作事项…")


def _extract_partial_json_string_field(payload: str, field_name: str) -> Optional[str]:
    marker = json.dumps(field_name)
    marker_index = payload.find(marker)
    if marker_index < 0:
        return None
    index = marker_index + len(marker)
    while index < len(payload) and payload[index].isspace():
        index += 1
    if index >= len(payload) or payload[index] != ":":
        return None
    index += 1
    while index < len(payload) and payload[index].isspace():
        index += 1
    if index >= len(payload) or payload[index] != '"':
        return None
    index += 1
    output: List[str] = []
    escapes = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while index < len(payload):
        character = payload[index]
        if character == '"':
            return "".join(output)
        if character != "\\":
            output.append(character)
            index += 1
            continue
        if index + 1 >= len(payload):
            break
        escaped = payload[index + 1]
        if escaped == "u":
            if index + 6 > len(payload):
                break
            digits = payload[index + 2 : index + 6]
            try:
                code_point = int(digits, 16)
            except ValueError:
                break
            if 0xD800 <= code_point <= 0xDBFF:
                if index + 12 > len(payload) or payload[index + 6 : index + 8] != "\\u":
                    break
                try:
                    low_surrogate = int(payload[index + 8 : index + 12], 16)
                except ValueError:
                    break
                if not 0xDC00 <= low_surrogate <= 0xDFFF:
                    break
                output.append(
                    chr(0x10000 + ((code_point - 0xD800) << 10) + (low_surrogate - 0xDC00))
                )
                index += 12
                continue
            if 0xDC00 <= code_point <= 0xDFFF:
                break
            output.append(chr(code_point))
            index += 6
            continue
        replacement = escapes.get(escaped)
        if replacement is None:
            break
        output.append(replacement)
        index += 2
    return "".join(output)


AgentOutputT = TypeVar("AgentOutputT", bound=BaseModel)
