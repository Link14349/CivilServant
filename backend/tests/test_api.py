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


def test_template_conversation_is_continuous_and_uses_one_action_point(monkeypatch) -> None:
    client = _client(monkeypatch)
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
    assert response.json()["active_scene"] is None


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
