from fastapi.testclient import TestClient

import civilservant.main as main_module
from civilservant.store import GameStore


def test_template_api_completes_six_turns(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "store", GameStore("sqlite:///:memory:"))
    client = TestClient(main_module.app)

    response = client.post(
        "/api/games",
        json={
            "player_name": "接口测试",
            "mode": "template",
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
            "seed": 20260826,
        },
    )
    assert response.status_code == 201
    game = response.json()

    choices = [
        "mayor_compliance",
        "phased_plan",
        "conditional_support",
        "record_dissent",
        "acknowledge_adjust",
        "transparent_review",
    ]
    for choice in choices:
        response = client.post(
            "/api/games/{}/actions".format(game["id"]),
            json={"version": game["version"], "option_id": choice},
        )
        assert response.status_code == 200
        game = response.json()

    assert game["status"] == "completed"
    assert len(game["history"]) == 6


def test_live_game_requires_key_for_action(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "store", GameStore("sqlite:///:memory:"))
    client = TestClient(main_module.app)
    game = client.post(
        "/api/games",
        json={
            "player_name": "接口测试",
            "mode": "live",
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
            "seed": 8,
        },
    ).json()

    response = client.post(
        "/api/games/{}/actions".format(game["id"]),
        json={"version": game["version"], "option_id": "mayor_compliance"},
    )
    assert response.status_code == 401
    assert "API Key" in response.json()["detail"]


def test_llm_validation_requires_key_header() -> None:
    client = TestClient(main_module.app)
    response = client.post(
        "/api/llm/validate",
        json={
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
        },
    )
    assert response.status_code == 401
    assert "API Key" in response.json()["detail"]


def test_template_conversation_updates_game_without_advancing_turn(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "store", GameStore("sqlite:///:memory:"))
    client = TestClient(main_module.app)
    game = client.post(
        "/api/games",
        json={
            "player_name": "会谈测试",
            "mode": "template",
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
            "seed": 9,
        },
    ).json()

    response = client.post(
        "/api/games/{}/conversations".format(game["id"]),
        json={
            "version": game["version"],
            "actor_id": "mayor",
            "channel": "private_meeting",
            "intent": "inquire",
            "message": "企业还能撑多久？",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["turn"]["number"] == 1
    assert updated["turn"]["attention_remaining"] == 2
    assert updated["conversations"][0]["actor_id"] == "mayor"


def test_cannot_talk_to_irrelevant_actor(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "store", GameStore("sqlite:///:memory:"))
    client = TestClient(main_module.app)
    game = client.post(
        "/api/games",
        json={"player_name": "测试", "mode": "template", "seed": 10},
    ).json()
    response = client.post(
        "/api/games/{}/conversations".format(game["id"]),
        json={
            "version": game["version"],
            "actor_id": "banker",
            "channel": "private_meeting",
            "intent": "inquire",
            "message": "说说情况。",
        },
    )
    assert response.status_code == 400
