import pytest

from civilservant.engine import (
    apply_action,
    apply_conversation,
    create_game,
    template_action,
    template_conversation,
    to_game_view,
)
from civilservant.models import ParsedConversation


CHOICES = [
    "mayor_compliance",
    "phased_plan",
    "conditional_support",
    "record_dissent",
    "acknowledge_adjust",
    "transparent_review",
]


def play_game(seed: int = 20260826):
    game = create_game(
        player_name="测试书记",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=seed,
    )
    for option_id in CHOICES:
        action, choice = template_action(game, option_id, None)
        game = apply_action(game, action, choice)
    return game


def test_six_turn_template_game_completes() -> None:
    game = play_game()
    view = to_game_view(game)

    assert game.status == "completed"
    assert game.turn_index == 6
    assert game.version == 7
    assert len(game.history) == 6
    assert view.turn is None
    assert view.outcome is not None
    assert view.outcome.grade in {"A", "B", "C", "D"}
    assert game.state["commitments"]


def test_same_seed_and_choices_are_deterministic() -> None:
    first = play_game()
    second = play_game()

    assert first.state == second.state
    assert first.history == second.history
    assert first.outcome == second.outcome


def test_different_strategy_changes_state() -> None:
    baseline = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    alternative = baseline.model_copy(deep=True)

    action_a, choice_a = template_action(baseline, "mayor_compliance", None)
    action_b, choice_b = template_action(alternative, "delay_for_jobs", None)

    baseline = apply_action(baseline, action_a, choice_a)
    alternative = apply_action(alternative, action_b, choice_b)

    assert baseline.state["metrics"] != alternative.state["metrics"]
    assert baseline.state["relations"] != alternative.state["relations"]


def test_custom_text_maps_without_inventing_an_option() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    action, choice = template_action(
        game,
        None,
        "期限不能突破，请市长牵头，不得新增隐性债务。",
    )

    assert action.strategy_tag == "mayor_compliance"
    assert "市长牵头" in action.directive_summary
    assert choice.startswith("其他：")


def test_conversation_uses_attention_without_advancing_turn() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    result = template_conversation(game, "mayor", "private_meeting", "inquire", "企业到底还能撑多久？")
    updated = apply_conversation(game, "mayor", "private_meeting", "inquire", "企业到底还能撑多久？", result)

    assert updated.turn_index == 0
    assert updated.version == 2
    assert updated.state["attention_remaining"] == 2
    assert updated.state["conversations"][0]["actor_id"] == "mayor"
    assert "一万一千二百" not in updated.state["conversations"][0]["reply"]


def test_actor_cannot_reference_another_actors_belief() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    leaked = ParsedConversation(
        reply="我知道县里的真实人数。",
        disposition="inform",
        used_belief_ids=["county_real_jobs"],
        consequence_note="错误泄漏。",
    )
    with pytest.raises(ValueError, match="不应知道"):
        apply_conversation(game, "mayor", "private_meeting", "inquire", "真实人数？", leaked)


def test_private_assignment_requires_formalization_and_can_join_decision() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    result = template_conversation(
        game,
        "mayor",
        "private_meeting",
        "private_assignment",
        "先准备首批关停方案，只向我报告。",
    )
    game = apply_conversation(
        game,
        "mayor",
        "private_meeting",
        "private_assignment",
        "先准备首批关停方案，只向我报告。",
        result,
    )
    assert game.state["private_records"][0]["status"] == "待正式化"

    action, choice = template_action(game, "mayor_compliance", None)
    game = apply_action(game, action, choice)
    assert game.state["private_records"][0]["status"] == "已纳入正式决定"
    assert game.state["attention_remaining"] == 3


def test_only_three_conversations_per_turn() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    for _ in range(3):
        result = template_conversation(game, "mayor", "private_meeting", "sound_out", "你怎么看？")
        game = apply_conversation(game, "mayor", "private_meeting", "sound_out", "你怎么看？", result)
    result = template_conversation(game, "mayor", "private_meeting", "sound_out", "再谈一次？")
    with pytest.raises(ValueError, match="已经用完"):
        apply_conversation(game, "mayor", "private_meeting", "sound_out", "再谈一次？", result)


def test_initial_player_view_does_not_leak_private_actor_context() -> None:
    game = create_game(
        player_name="甲",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=7,
    )
    payload = to_game_view(game).model_dump_json()
    assert "private_goal" not in payload
    assert "county_real_jobs" not in payload
    assert "一万一千二百" not in payload
    assert "六千八百万元" not in payload
