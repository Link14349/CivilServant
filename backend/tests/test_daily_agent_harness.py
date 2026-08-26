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
from civilservant.daily_llm import DailyAgentProvider
from civilservant.daily_models import (
    AgentToolCall,
    AgentToolEffect,
    AgentUtterance,
    PostSceneResult,
)
from civilservant.daily_scenario import ACTORS, STANDING_COMMITTEE_MEMBER_IDS


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
        self.payloads = []

    def _request(self, api_key, game, payload, max_tokens):
        self.payloads.append(payload)
        if len(self.payloads) == 1:
            return {
                "tool_calls": [
                    {
                        "call_id": "contacts-1",
                        "name": "list_contacts",
                        "arguments": {"query": "财政"},
                    }
                ],
                "final": None,
            }
        return {
            "tool_calls": [],
            "final": {
                "text": "我会先让财政部门说明边界。",
                "used_belief_ids": [],
            },
        }


def test_live_agent_loop_executes_tool_then_forms_final_reply() -> None:
    current = start_conversation(
        game(mode="live"),
        idempotency_key="start-live-loop",
        actor_id="mayor",
        channel="private_meeting",
    )
    provider = _LoopProvider()
    result = provider.resolve_conversation(
        api_key="test-key",
        game=current,
        actor_id="mayor",
        player_message="财政边界由谁先说明？",
    )
    assert result.text == "我会先让财政部门说明边界。"
    assert len(provider.payloads) == 2
    assert provider.payloads[1]["tool_results"][0]["ok"] is True
    assert any(item["id"] == "finance_director" for item in provider.payloads[1]["tool_results"][0]["data"])
