import json
from copy import deepcopy

import pytest

import civilservant.daily_llm as daily_llm_module
from civilservant.daily_agent_tools import execute_agent_tool
from civilservant.daily_engine import (
    act_on_document,
    actor_agent_projection,
    add_conversation_reply,
    close_day,
    close_scene,
    create_daily_game,
    start_conversation,
)
from civilservant.daily_llm import DailyAgentProvider, _extract_partial_json_string_field
from civilservant.daily_models import (
    AgentToolCall,
    AgentToolEffect,
    AgentUtterance,
    PostSceneResult,
)
from civilservant.daily_scenario import ACTORS, STANDING_COMMITTEE_MEMBER_IDS
from civilservant.llm import LlmError


def game(mode: str = "template"):
    return create_daily_game(
        player_name="测试书记",
        background="general",
        mode=mode,
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=20260826,
    )


def test_municipal_actor_knows_public_roster_without_private_context() -> None:
    projection = actor_agent_projection(game(), "mayor")
    known_people = {item["id"]: item for item in projection["known_people"]}
    assert set(STANDING_COMMITTEE_MEMBER_IDS) - {"mayor"} <= set(known_people)
    assert {"finance_director", "county_secretary", "chairman", "banker"} <= set(known_people)
    assert all("private_goal" not in item and "beliefs" not in item for item in known_people.values())
    assert "county_real_jobs" not in str(projection)


def test_every_actor_has_a_nonempty_acquaintance_roster() -> None:
    current = game()
    for actor_id in ACTORS:
        projection = actor_agent_projection(current, actor_id)
        assert projection["known_people"], actor_id


def test_file_tools_enforce_visibility_and_can_read_full_forwarded_file() -> None:
    current = game()
    denied, effect = execute_agent_tool(
        current,
        "mayor",
        "interaction",
        AgentToolCall(call_id="read-denied", name="read_file", arguments={"document_id": "doc-flood"}),
        [],
    )
    assert denied["ok"] is False
    assert effect is None

    current = act_on_document(
        current,
        idempotency_key="forward-flood-to-mayor",
        document_id="doc-flood",
        operation="forward",
        note="",
        recipient_id="mayor",
    )
    allowed, effect = execute_agent_tool(
        current,
        "mayor",
        "interaction",
        AgentToolCall(call_id="read-allowed", name="read_file", arguments={"document_id": "doc-flood"}),
        [],
    )
    assert allowed["ok"] is True
    assert "临时围挡" in allowed["data"]["content"]
    assert effect is None


def test_committed_utterance_atomically_applies_staged_file_write() -> None:
    current = start_conversation(
        game(),
        idempotency_key="start-tool-talk",
        actor_id="mayor",
        channel="private_meeting",
    )
    tool_result, effect = execute_agent_tool(
        current,
        "mayor",
        "interaction",
        AgentToolCall(
            call_id="write-note",
            name="write_file",
            arguments={
                "title": "市政府资金边界便笺",
                "document_type": "note",
                "summary": "列明需要财政核实的边界。",
                "content": "现有口径只能作为风险提示，新增承诺需要重新测算。",
                "source_document_ids": [],
                "deliver_to_ids": ["player"],
            },
        ),
        [],
    )
    assert tool_result["ok"] is True
    assert effect is not None
    current = add_conversation_reply(
        current,
        utterance=AgentUtterance(
            text="我先形成一份便笺供你查看。",
            used_belief_ids=[],
            tool_effects=[effect],
        ),
    )
    document = next(item for item in current.state["documents"] if item["title"] == "市政府资金边界便笺")
    assert document["author_id"] == "mayor"
    assert document["recipient_ids"] == ["mayor", "player"]
    assert document["status"] == "ready"


def test_settlement_tools_store_structured_memory_todo_and_commitment() -> None:
    current = start_conversation(
        game(),
        idempotency_key="start-settlement-talk",
        actor_id="mayor",
        channel="private_meeting",
        opening="请三日内组织财政测算，重大承诺仍需按程序研究。",
    )
    scene = current.state["active_scene"]
    result = PostSceneResult(
        memory="书记要求先测算，不先作资金承诺。",
        relationship_signal="improved",
        tool_effects=[
            AgentToolEffect(
                kind="record_knowledge",
                payload={
                    "claim": "书记要求先完成资金边界测算，再讨论新增承诺。",
                    "source_type": "transcript",
                    "source_id": scene["transcript"][0]["id"],
                    "confidence": "high",
                    "related_actor_ids": ["player"],
                    "related_issue_ids": ["fiscal_priorities"],
                },
            ),
            AgentToolEffect(
                kind="record_memory",
                payload={
                    "summary": "书记要求先测算，不先作资金承诺。",
                    "memory_type": "episodic",
                    "importance": 4,
                    "related_actor_ids": ["player"],
                    "related_issue_ids": ["fiscal_priorities"],
                    "source_turn_ids": [scene["transcript"][0]["id"]],
                },
            ),
            AgentToolEffect(
                kind="record_todo",
                payload={
                    "summary": "组织财政部门完成资金边界测算。",
                    "due_date": "2026-09-04",
                    "priority": "high",
                    "requires_formal_decision": False,
                    "related_actor_ids": ["finance_director"],
                    "related_issue_ids": ["fiscal_priorities"],
                },
            ),
            AgentToolEffect(
                kind="record_relationship_impression",
                payload={
                    "target_id": "player",
                    "signal": "improved",
                    "note": "书记尊重政府方案形成和资金测算程序。",
                    "related_issue_id": "fiscal_priorities",
                },
            ),
            AgentToolEffect(
                kind="record_commitment",
                payload={
                    "commitment_type": "instruction",
                    "giver_id": "player",
                    "receiver_id": "mayor",
                    "summary": "三日内组织财政测算。",
                    "condition": None,
                    "due_date": "2026-09-04",
                    "visibility": "private",
                    "requires_formal_decision": False,
                },
            ),
        ],
    )
    current = close_scene(
        current,
        idempotency_key="close-settlement-talk",
        record_version=scene["record_version"],
        post_scene_results={"mayor": result},
    )
    runtime = current.state["actor_runtime"]["mayor"]
    assert runtime["memories"][-1]["importance"] == 4
    assert runtime["tasks"][-1]["priority"] == "high"
    assert runtime["knowledge"][-1]["confidence"] == "high"
    assert runtime["relationships"]["player"]["note"] == "书记尊重政府方案形成和资金测算程序。"
    assert current.state["commitments"][-1]["receiver_id"] == "mayor"
    assert current.state["relations"]["mayor"] == 51
    assert current.state["scene_archive"][-1]["id"] == scene["id"]
    projection = actor_agent_projection(current, "mayor")
    assert any(item["summary"] == "三日内组织财政测算。" for item in projection["commitments"])
    record_result, effect = execute_agent_tool(
        current,
        "mayor",
        "interaction",
        AgentToolCall(
            call_id="read-frozen-scene",
            name="read_scene_record",
            arguments={"scene_id": scene["id"]},
        ),
        [],
    )
    assert record_result["ok"] is True
    assert record_result["data"]["transcript"][0]["text"].startswith("请三日内")
    assert effect is None


def test_handled_document_moves_to_archive_when_next_day_begins() -> None:
    current = act_on_document(
        game(),
        idempotency_key="annotate-before-archive",
        document_id="doc-environment",
        operation="annotate",
        note="请补充就业影响后再研究。",
        recipient_id=None,
    )
    current = close_day(current, idempotency_key="advance-and-archive")
    handled = next(item for item in current.state["documents"] if item["id"] == "doc-environment")
    untouched = next(item for item in current.state["documents"] if item["id"] == "doc-flood")
    assert handled["status"] == "archived"
    assert untouched["status"] == "received"
    assert all(item["document_id"] != "doc-environment" for item in current.state["briefing"])


class _LoopProvider(DailyAgentProvider):
    def __init__(self) -> None:
        super().__init__()
        self.bodies = []

    def _post_chat(self, api_key, game, body):
        self.bodies.append(deepcopy(body))
        if len(self.bodies) == 1:
            return {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "contacts-1",
                                    "type": "function",
                                    "function": {
                                        "name": "list_contacts",
                                        "arguments": json.dumps({"query": "财政"}),
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "final-1",
                                "type": "function",
                                "function": {
                                    "name": "submit_final_result",
                                    "arguments": json.dumps(
                                        {
                                            "text": "我会先让财政部门说明边界。",
                                            "used_belief_ids": [],
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_live_agent_loop_executes_tool_then_forms_final_reply() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-live-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    provider = _LoopProvider()
    traces = []
    result = provider.resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="财政边界由谁先说明？",
        on_trace=traces.append,
    )
    assert result.text == "我会先让财政部门说明边界。"
    assert len(provider.bodies) == 2
    first_body = provider.bodies[0]
    assert first_body["tool_choice"] == "required"
    assert "response_format" not in first_body
    assert "最多 128 轮" in first_body["messages"][0]["content"]
    assert "第 32 轮起" in first_body["messages"][0]["content"]
    loop_prompt = json.loads(first_body["messages"][1]["content"])["agent_loop"]
    assert loop_prompt["preferred_completion_rounds"] == 32
    assert loop_prompt["maximum_rounds"] == 128
    assert "避免重复调用同一工具" in loop_prompt["rule"]
    functions = {item["function"]["name"]: item["function"] for item in first_body["tools"]}
    assert "list_contacts" in functions
    assert functions["list_contacts"]["parameters"]["type"] == "object"
    assert "submit_final_result" in functions
    tool_message = provider.bodies[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    tool_result = json.loads(tool_message["content"])
    assert tool_result["ok"] is True
    assert any(item["id"] == "finance_director" for item in tool_result["data"])
    assert any(item["kind"] == "tool_call" for item in traces)
    assert any(item["kind"] == "tool_result" for item in traces)
    assert traces[-1]["kind"] == "agent_complete"


class _RepeatedToolProvider(DailyAgentProvider):
    def __init__(self) -> None:
        super().__init__()
        self.bodies = []

    def _post_chat(self, api_key, game, body):
        self.bodies.append(deepcopy(body))
        if isinstance(body["tool_choice"], dict):
            return {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "forced-final",
                                    "type": "function",
                                    "function": {
                                        "name": "submit_final_result",
                                        "arguments": json.dumps(
                                            {"text": "不再重复查询，先按已知情况答复。", "used_belief_ids": []},
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "repeat-{}".format(len(self.bodies)),
                                "type": "function",
                                "function": {
                                    "name": "list_contacts",
                                    "arguments": json.dumps({"query": "财政"}),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_repeated_tool_call_triggers_named_final_tool_choice() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-repeated-tool-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    provider = _RepeatedToolProvider()
    traces = []
    result = provider.resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="请说明财政边界。",
        on_trace=traces.append,
    )
    assert result.text.startswith("不再重复查询")
    assert len(provider.bodies) == 3
    assert provider.bodies[2]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_final_result"},
    }
    assert any(item["kind"] == "convergence_guard" for item in traces)
    duplicate_result = json.loads(provider.bodies[2]["messages"][-1]["content"])
    assert duplicate_result["duplicate_count"] == 2


class _InvalidFinalProvider(DailyAgentProvider):
    def _post_chat(self, api_key, game, body):
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "invalid-final",
                                "type": "function",
                                "function": {
                                    "name": "submit_final_result",
                                    "arguments": json.dumps({"text": ""}),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_repeated_invalid_final_uses_safe_spoken_fallback() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-invalid-final-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    traces = []
    result = _InvalidFinalProvider().resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="请说明情况。",
        on_trace=traces.append,
    )
    assert result.text == "这件事我还需要进一步核实，暂时不能给出可靠答复。"
    assert traces[-1]["kind"] == "safe_fallback"


class _UniqueUntilForcedProvider(DailyAgentProvider):
    def __init__(self) -> None:
        super().__init__()
        self.bodies = []

    def _post_chat(self, api_key, game, body):
        self.bodies.append(deepcopy(body))
        if isinstance(body["tool_choice"], dict):
            tool_name = "submit_final_result"
            arguments = {"text": "已到收敛轮次，按现有材料答复。", "used_belief_ids": []}
        else:
            tool_name = "list_contacts"
            arguments = {"query": "查询-{}".format(len(self.bodies))}
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-{}".format(len(self.bodies)),
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(arguments, ensure_ascii=False),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_round_32_forces_named_final_tool_but_keeps_128_hard_limit() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-force-round-32",
        actor_id="mayor",
        channel="private_meeting",
    )
    provider = _UniqueUntilForcedProvider()
    result = provider.resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="请广泛核对后回答。",
    )
    assert result.text.startswith("已到收敛轮次")
    assert len(provider.bodies) == 32
    assert provider.bodies[30]["tool_choice"] == "required"
    assert provider.bodies[31]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_final_result"},
    }
    assert daily_llm_module.MAX_AGENT_LOOP_ROUNDS == 128


class _LengthProvider(DailyAgentProvider):
    def _post_chat(self, api_key, game, body):
        return {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None, "tool_calls": []},
                }
            ]
        }


def test_native_agent_loop_reports_output_truncation_explicitly() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-length-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    with pytest.raises(LlmError, match="达到输出上限并被截断"):
        _LengthProvider().resolve_conversation(
            api_key="test-key",
            game=current,
            actor_id="mayor",
            player_message="请说明情况。",
        )


class _RepairArgumentsProvider(DailyAgentProvider):
    def __init__(self) -> None:
        super().__init__()
        self.bodies = []

    def _post_chat(self, api_key, game, body):
        self.bodies.append(deepcopy(body))
        if len(self.bodies) == 1:
            return {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "broken-arguments",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"document_id":',
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "final-after-repair",
                                "type": "function",
                                "function": {
                                    "name": "submit_final_result",
                                    "arguments": json.dumps(
                                        {"text": "刚才的工具参数无效，我先说明已知边界。", "used_belief_ids": []},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_native_agent_loop_returns_tool_argument_error_for_model_repair() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-repair-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    provider = _RepairArgumentsProvider()
    result = provider.resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="请读材料后说明。",
    )
    assert result.text.startswith("刚才的工具参数无效")
    repair_message = provider.bodies[1]["messages"][-1]
    assert repair_message["role"] == "tool"
    assert "error_position" in repair_message["content"]


def test_partial_final_tool_arguments_expose_only_complete_string_characters() -> None:
    assert _extract_partial_json_string_field('{"text":"岚州', "text") == "岚州"
    assert _extract_partial_json_string_field('{"text":"第一行\\n第二', "text") == "第一行\n第二"
    assert _extract_partial_json_string_field('{"used_belief_ids":[],"text":"回应"}', "text") == "回应"
    assert _extract_partial_json_string_field('{"text":"尚未完成\\u5c', "text") == "尚未完成"
    assert _extract_partial_json_string_field('{"text":"完成\\ud83d\\udc4d"}', "text") == "完成👍"


class _StreamingProvider(DailyAgentProvider):
    def _post_chat_stream(self, api_key, game, body, *, on_text_update, is_cancelled):
        assert body["stream"] is True
        on_text_update("我")
        on_text_update("我会先核对财政边界。")
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "stream-final",
                                "type": "function",
                                "function": {
                                    "name": "submit_final_result",
                                    "arguments": json.dumps(
                                        {
                                            "text": "我会先核对财政边界。",
                                            "used_belief_ids": [],
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    },
                }
            ]
        }


def test_agent_loop_forwards_incremental_final_text_updates() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-stream-callback",
        actor_id="mayor",
        channel="private_meeting",
    )
    updates = []
    statuses = []
    result = _StreamingProvider().resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="财政边界是什么？",
        on_text_update=updates.append,
        on_status=statuses.append,
        is_cancelled=lambda: False,
    )
    assert result.text == "我会先核对财政边界。"
    assert updates[:2] == ["我", "我会先核对财政边界。"]
    assert statuses[-1] == "发言生成完成，正在写入会议记录…"


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def iter_lines(self):
        yield from self.lines


def test_deepseek_sse_tool_arguments_are_reassembled_and_exposed_as_text(monkeypatch) -> None:
    def event(delta, finish_reason=None):
        return "data: " + json.dumps(
            {"choices": [{"delta": delta, "finish_reason": finish_reason}]},
            ensure_ascii=False,
        )

    lines = [
        event(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-final",
                        "type": "function",
                        "function": {
                            "name": "submit_",
                            "arguments": '{"text":"岚',
                        },
                    }
                ]
            }
        ),
        event(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {
                            "name": "final_result",
                            "arguments": "州逐",
                        },
                    }
                ]
            }
        ),
        event(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {
                            "arguments": '字","used_belief_ids":[]}',
                        },
                    }
                ]
            }
        ),
        event({}, "tool_calls"),
        "data: [DONE]",
    ]
    monkeypatch.setattr(
        daily_llm_module.httpx,
        "stream",
        lambda *args, **kwargs: _FakeStreamResponse(lines),
    )
    updates = []
    response = DailyAgentProvider()._post_chat_stream(
        "test-key",
        game(mode="live"),
        {"stream": True},
        on_text_update=updates.append,
        is_cancelled=lambda: False,
    )
    tool_call = response["choices"][0]["message"]["tool_calls"][0]
    assert tool_call["id"] == "call-final"
    assert tool_call["function"]["name"] == "submit_final_result"
    assert json.loads(tool_call["function"]["arguments"])["text"] == "岚州逐字"
    assert updates == ["岚州逐", "岚州逐字"]
