import time

from fastapi.testclient import TestClient

import civilservant.main as main_module
from civilservant.store import GameStore


def _client(monkeypatch):
    monkeypatch.setattr(main_module, "store", GameStore("sqlite:///:memory:"))
    return TestClient(main_module.app)


def _new_game(client: TestClient, mode: str = "template") -> dict:
    response = client.post(
        "/api/games",
        json={
            "player_name": "接口测试",
            "background": "general",
            "mode": mode,
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
            "seed": 20260826,
        },
    )
    assert response.status_code == 201
    return response.json()


def _command(game: dict, **extra) -> dict:
    return {
        "version": game["version"],
        "idempotency_key": "test-key-{}-{}".format(game["version"], extra.get("suffix", "x")),
        **{key: value for key, value in extra.items() if key != "suffix"},
    }


def _wait_for_generation(client: TestClient, game: dict, timeout: float = 4.0) -> dict:
    deadline = time.monotonic() + timeout
    current = game
    while time.monotonic() < deadline:
        response = client.get("/api/games/{}".format(game["id"]))
        assert response.status_code == 200
        current = response.json()
        scene = current.get("active_scene")
        if not scene or scene["generation"]["status"] != "thinking":
            return current
        time.sleep(0.03)
    raise AssertionError("人物流式生成未在测试时限内完成")


def test_agent_debug_trace_redacts_keys_and_keeps_unique_sequences() -> None:
    game_id = "debug-redaction-game"
    trace_id = "debug-redaction-trace"
    main_module._register_agent_trace(game_id, trace_id, "mayor", "周立衡", "test")
    for index in range(main_module.MAX_AGENT_TRACE_EVENTS + 3):
        main_module._append_agent_trace(
            game_id,
            trace_id,
            {
                "kind": "tool_call",
                "round": index + 1,
                "title": "调试事件",
                    "payload": {
                        "name": "read_file",
                        "arguments": {"document_id": "private-doc", "content": "private-content"},
                        "api_key": "secret-value",
                    "authorization": "Bearer sk-abcdefghijk",
                    "content": "不要暴露 sk-1234567890",
                },
            },
        )
    trace = main_module.agent_debug_traces[game_id]
    serialized = str(trace)
    assert "secret-value" not in serialized
    assert "sk-abcdefghijk" not in serialized
    assert "sk-1234567890" not in serialized
    assert "private-content" not in serialized
    assert len(trace["events"]) == main_module.MAX_AGENT_TRACE_EVENTS
    assert trace["dropped_event_count"] == 3
    sequences = [event["sequence"] for event in trace["events"]]
    assert sequences == sorted(set(sequences))
    main_module.agent_debug_traces.pop(game_id, None)


def test_batch_trace_waits_for_batch_completion_and_hides_private_results() -> None:
    game_id = "debug-batch-game"
    trace_id = "debug-batch-trace"
    main_module._register_agent_trace(
        game_id,
        trace_id,
        None,
        "场景结算",
        "post_scene_settlement",
    )
    main_module._append_agent_trace(
        game_id,
        trace_id,
        {
            "kind": "agent_complete",
            "round": 2,
            "actor_id": "mayor",
            "title": "一个人物完成结算",
            "payload": {
                "result": {
                    "memory": "不应展示的私人判断",
                    "relationship_signal": "strained",
                    "intents": [{"summary": "不应展示的私下动作"}],
                    "tool_effects": [{"kind": "record_memory"}],
                }
            },
        },
    )
    trace = main_module.agent_debug_traces[game_id]
    assert trace["status"] == "running"
    assert "不应展示" not in str(trace)
    assert trace["events"][0]["payload"]["result"] == {
        "result_fields": ["intents", "memory", "relationship_signal", "tool_effects"],
        "intent_count": 1,
        "tool_effect_count": 1,
    }
    main_module._append_agent_trace(
        game_id,
        trace_id,
        {
            "kind": "batch_complete",
            "round": 0,
            "title": "所有人物完成结算",
            "payload": {"actor_ids": ["mayor"]},
        },
    )
    assert trace["status"] == "completed"
    main_module.agent_debug_traces.pop(game_id, None)


def test_create_daily_game_and_close_day(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client)
    assert game["day_number"] == 1
    assert game["action_budget"]["remaining"] == 4
    assert len(game["documents"]) >= 5
    assert len(game["briefing"]) >= 5
    assert len(game["actors"]) == 37
    assert len(game["reference_materials"]) == 10
    assert {item["id"] for item in game["reference_materials"]} >= {
        "ref-city-economy",
        "ref-beishan",
        "ref-nanchuan",
    }
    nanchuan = next(actor for actor in game["actors"] if actor["id"] == "nanchuan_secretary")
    assert nanchuan["title"] == "南川区委书记"
    assert nanchuan["directory_group"] == "县区主官"
    finance = next(actor for actor in game["actors"] if actor["id"] == "finance_director")
    assert finance["title"] == "市财政局局长"
    assert finance["directory_group"] == "市直部门"

    response = client.post(
        "/api/games/{}/days/current/close".format(game["id"]),
        json=_command(game, suffix="close"),
    )
    assert response.status_code == 200
    next_day = response.json()
    assert next_day["day_number"] == 2
    assert next_day["current_date"] > game["current_date"]


def test_meeting_api_distributes_preselected_and_temporary_materials(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client)
    response = client.post(
        "/api/games/{}/meetings".format(game["id"]),
        json=_command(
            game,
            suffix="meeting-materials",
            meeting_type="coordination",
            discussion_mode="chaired",
            title="材料核对会",
            agenda="核对整改和财政口径",
            participant_ids=["mayor", "environment_director"],
            meeting_document_ids=["doc-environment"],
        ),
    )
    assert response.status_code == 200
    game = response.json()
    scene = game["active_scene"]
    assert scene["meeting_materials"][0]["document_id"] == "doc-environment"
    assert set(scene["meeting_materials"][0]["audience_ids"]) == {
        "player",
        "mayor",
        "environment_director",
    }

    response = client.post(
        "/api/games/{}/scenes/{}/materials".format(game["id"], scene["id"]),
        json=_command(
            game,
            suffix="temporary-material",
            record_version=scene["record_version"],
            document_ids=["doc-fiscal-note"],
        ),
    )
    assert response.status_code == 200
    updated = response.json()
    assert [
        item["document_id"] for item in updated["active_scene"]["meeting_materials"]
    ] == ["doc-environment", "doc-fiscal-note"]
    assert updated["active_scene"]["meeting_materials"][-1]["distribution_kind"] == "during_meeting"
    assert "临时向全体与会者发送" in updated["active_scene"]["transcript"][-1]["text"]


def test_template_conversation_is_continuous_and_uses_one_action_point(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        game = _new_game(client)
        response = client.post(
            "/api/games/{}/conversations".format(game["id"]),
            json=_command(game, suffix="start-talk", actor_id="mayor", channel="private_meeting"),
        )
        assert response.status_code == 200
        game = response.json()
        assert game["action_budget"]["remaining"] == 3
        scene = game["active_scene"]

        response = client.post(
            "/api/games/{}/scenes/{}/player-speeches".format(game["id"], scene["id"]),
            json=_command(
                game,
                suffix="talk-1",
                record_version=scene["record_version"],
                text="财政和企业现金流的真实边界是什么？",
            ),
        )
        assert response.status_code == 200
        game = response.json()
        assert game["active_scene"]["generation"]["status"] == "thinking"
        game = _wait_for_generation(client, game)
        assert len(game["active_scene"]["transcript"]) == 2
        assert game["action_budget"]["remaining"] == 3

        response = client.post(
            "/api/games/{}/scenes/{}/close".format(game["id"], scene["id"]),
            json=_command(
                game,
                suffix="close-talk",
                record_version=game["active_scene"]["record_version"],
            ),
        )
        assert response.status_code == 200
        game = response.json()
        assert game["active_scene"] is None
        assert any(item["title"] == "与周立衡进行了面谈" for item in game["activity"])
        assert "财政和企业现金流" not in str(game["activity"])


def test_notebook_can_be_used_during_conversation_and_stays_out_of_activity(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client)
    started = client.post(
        "/api/games/{}/conversations".format(game["id"]),
        json=_command(game, suffix="notebook-talk", actor_id="mayor", channel="private_meeting"),
    )
    assert started.status_code == 200
    game = started.json()
    remaining = game["action_budget"]["remaining"]
    response = client.post(
        "/api/games/{}/notebook-notes".format(game["id"]),
        json=_command(
            game,
            suffix="create-note",
            title="面谈要点",
            content="追问财政边界，不进入人物上下文。",
        ),
    )
    assert response.status_code == 200
    game = response.json()
    assert game["action_budget"]["remaining"] == remaining
    assert game["notebook_notes"][0]["title"] == "面谈要点"
    assert "追问财政边界" not in str(game["activity"])

    note = game["notebook_notes"][0]
    response = client.patch(
        "/api/games/{}/notebook-notes/{}".format(game["id"], note["id"]),
        json=_command(
            game,
            suffix="update-note",
            operation="update",
            content="已追问，待看文件附件。",
        ),
    )
    assert response.status_code == 200
    game = response.json()
    assert game["notebook_notes"][0]["content"] == "已追问，待看文件附件。"

    response = client.patch(
        "/api/games/{}/notebook-notes/{}".format(game["id"], note["id"]),
        json=_command(game, suffix="delete-note", operation="delete"),
    )
    assert response.status_code == 200
    assert response.json()["notebook_notes"] == []


def test_idempotency_returns_current_state_without_double_spend(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client)
    body = {
        "version": game["version"],
        "idempotency_key": "same-conversation-command",
        "actor_id": "mayor",
        "channel": "private_meeting",
    }
    first = client.post("/api/games/{}/conversations".format(game["id"]), json=body)
    assert first.status_code == 200
    second = client.post("/api/games/{}/conversations".format(game["id"]), json=body)
    assert second.status_code == 200
    assert second.json()["version"] == first.json()["version"]
    assert second.json()["action_budget"]["remaining"] == 3


def test_live_conversation_reply_requires_key(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client, mode="live")
    started = client.post(
        "/api/games/{}/conversations".format(game["id"]),
        json=_command(game, suffix="start-live", actor_id="mayor", channel="private_meeting"),
    )
    assert started.status_code == 200
    game = started.json()
    scene = game["active_scene"]
    response = client.post(
        "/api/games/{}/scenes/{}/player-speeches".format(game["id"], scene["id"]),
        json=_command(
            game,
            suffix="speak-live",
            record_version=scene["record_version"],
            text="说说情况。",
        ),
    )
    assert response.status_code == 401


def test_live_post_scene_settlement_requires_key(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client, mode="live")
    started = client.post(
        "/api/games/{}/conversations".format(game["id"]),
        json=_command(game, suffix="start-live-close", actor_id="mayor", channel="private_meeting"),
    )
    game = started.json()
    scene = game["active_scene"]
    response = client.post(
        "/api/games/{}/scenes/{}/close".format(game["id"], scene["id"]),
        json=_command(
            game,
            suffix="close-live-without-key",
            record_version=scene["record_version"],
        ),
    )
    assert response.status_code == 401


def test_document_task_arrives_next_day(monkeypatch) -> None:
    client = _client(monkeypatch)
    game = _new_game(client)
    response = client.post(
        "/api/games/{}/document-tasks".format(game["id"]),
        json=_command(
            game,
            suffix="draft",
            author_id="secretary_general",
            title="北山整改简要情况",
            document_type="report",
            instructions="区分已核实事实和待核实就业口径。",
            source_document_ids=["doc-environment", "doc-county-request"],
        ),
    )
    assert response.status_code == 200
    game = response.json()
    assert game["pending_tasks"]
    response = client.post(
        "/api/games/{}/days/current/close".format(game["id"]),
        json=_command(game, suffix="next-day"),
    )
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["documents"]}
    assert "北山整改简要情况" in titles
