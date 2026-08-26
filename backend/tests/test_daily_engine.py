from civilservant.daily_engine import (
    actor_agent_projection,
    add_player_speech,
    begin_meeting_generation,
    close_day,
    close_scene,
    commit_meeting_speech,
    create_daily_game,
    create_document_task,
    schedule_calendar_entry,
    start_field_visit,
    start_meeting,
    submit_document,
    template_meeting_utterance,
    to_daily_game_view,
)
from civilservant.daily_models import PostSceneResult, SuperiorReaction


def game(seed: int = 20260826):
    return create_daily_game(
        player_name="测试书记",
        background="general",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=seed,
    )


def test_seven_day_template_replay_without_fixed_story() -> None:
    current = game()
    for day in range(1, 8):
        while current.state.get("active_scene"):
            scene = current.state["active_scene"]
            current = close_scene(
                current,
                idempotency_key="close-scene-{}-{}".format(day, scene["id"]),
                record_version=scene["record_version"],
            )
        if day < 7:
            current = close_day(current, idempotency_key="close-day-{}".format(day))
    assert current.state["day_number"] == 7
    assert current.status == "active"
    assert current.state["current_date"] == "2026-09-07"


def test_scheduled_field_visit_reserves_then_spends_on_execution_day() -> None:
    current = game()
    current = schedule_calendar_entry(
        current,
        idempotency_key="schedule-field",
        target_date="2026-09-02",
        kind="field_visit",
        title="不打招呼调研北山园区",
        participant_ids=[],
        location_id="beishan_park",
        meeting_type=None,
        discussion_mode=None,
        notified=False,
    )
    assert current.state["action_remaining"] == 4
    current = close_day(current, idempotency_key="close-day-one")
    assert current.state["action_remaining"] == 2
    assert current.state["active_scene"]["kind"] == "field_visit"
    assert "样本" in current.state["active_scene"]["transcript"][0]["text"] or "口径" in current.state["active_scene"]["transcript"][0]["text"]


def test_meeting_generation_uses_record_lease_and_player_can_cancel() -> None:
    current = start_meeting(
        game(),
        idempotency_key="start-meeting",
        meeting_type="symposium",
        discussion_mode="chaired",
        title="北山产业座谈会",
        agenda="核实就业和资产条件",
        participant_ids=["mayor", "county_secretary", "chairman", "environment_director"],
    )
    scene = current.state["active_scene"]
    current, selected = begin_meeting_generation(
        current,
        idempotency_key="nominate-mayor",
        record_version=scene["record_version"],
        nominated_actor_id="mayor",
    )
    assert selected == "mayor"
    generation_id = current.state["active_scene"]["generation"]["id"]
    current = add_player_speech(
        current,
        idempotency_key="interrupt",
        record_version=current.state["active_scene"]["record_version"],
        text="先停一下，我要把问题限定在资金来源。",
    )
    assert current.state["active_scene"]["generation"]["status"] == "canceled"
    try:
        commit_meeting_speech(
            current,
            generation_id=generation_id,
            actor_id="mayor",
            utterance=template_meeting_utterance(current, "mayor"),
        )
    except ValueError as exc:
        assert "失效" in str(exc)
    else:
        raise AssertionError("取消的生成不应能够提交")


def test_actor_projection_does_not_contain_other_private_beliefs() -> None:
    projection = actor_agent_projection(game(), "mayor")
    serialized = str(projection)
    assert "mayor_cash_crisis" in serialized
    assert "county_real_jobs" not in serialized
    assert "chairman_collateral_truth" not in serialized


def test_document_submission_preserves_source_and_creates_delayed_reaction() -> None:
    current = create_document_task(
        game(),
        idempotency_key="draft-report",
        author_id="secretary_general",
        title="报省委简要情况",
        document_type="report",
        instructions="说明就业数据仍待核实。",
        source_document_ids=["doc-county-request"],
    )
    current = close_day(current, idempotency_key="advance")
    document = next(item for item in current.state["documents"] if item["title"] == "报省委简要情况")
    current = submit_document(
        current,
        idempotency_key="submit-report",
        document_id=document["id"],
        recipient_id="superior",
        cover_note="请审阅。",
    )
    submitted = next(item for item in current.state["documents"] if item["id"] == document["id"])
    assert submitted["source_document_ids"] == ["doc-county-request"]
    assert submitted["status"] == "submitted"
    assert any(item["kind"] == "superior_document_reaction" for item in current.state["delayed_triggers"])


def test_player_view_does_not_expose_actor_private_memory() -> None:
    current = game()
    current.state["actor_runtime"]["mayor"]["memories"].append(
        {"date": "2026-09-01", "summary": "只供市长本人使用的私人判断"}
    )
    view = to_daily_game_view(current).model_dump_json()
    assert "只供市长本人使用的私人判断" not in view


def test_same_seed_produces_same_field_observation() -> None:
    first = start_field_visit(
        game(1234),
        idempotency_key="field-a",
        location_id="flood_site",
        notified=False,
    )
    second = start_field_visit(
        game(1234),
        idempotency_key="field-b",
        location_id="flood_site",
        notified=False,
    )
    assert (
        first.state["active_scene"]["transcript"][0]["text"]
        == second.state["active_scene"]["transcript"][0]["text"]
    )


def test_post_scene_agent_intents_are_validated_into_tasks_not_direct_world_changes() -> None:
    current = start_meeting(
        game(),
        idempotency_key="meeting-for-settlement",
        meeting_type="coordination",
        discussion_mode="chaired",
        title="口径核实协调会",
        agenda="只核实事实",
        participant_ids=["mayor", "secretary_general"],
    )
    scene = current.state["active_scene"]
    results = {
        "mayor": PostSceneResult.model_validate(
            {
                "memory": "书记要求先核实资金责任。",
                "intents": [
                    {
                        "kind": "contact_actor",
                        "summary": "会后请秘书长核对材料版本。",
                        "target_id": "secretary_general",
                        "requires_formal_decision": False,
                    },
                    {
                        "kind": "propose_action",
                        "summary": "建议由市政府准备财政方案。",
                        "requires_formal_decision": True,
                    },
                ],
            }
        ),
        "secretary_general": PostSceneResult.model_validate(
            {
                "memory": "需要整理不同材料的修改痕迹。",
                "intents": [
                    {
                        "kind": "draft_document",
                        "summary": "整理三份口径差异。",
                        "title": "材料口径差异表",
                        "requires_formal_decision": False,
                    }
                ],
            }
        ),
    }
    current = close_scene(
        current,
        idempotency_key="settle-with-agents",
        record_version=scene["record_version"],
        post_scene_results=results,
    )
    assert any(task["title"] == "材料口径差异表" for task in current.state["document_tasks"])
    assert any(note["title"] == "会后行动建议待决" for note in current.state["notifications"])
    planned = current.state["actor_runtime"]["mayor"]["tasks"]
    assert planned[0]["status"] == "awaiting_formal_decision"
    assert current.state["metrics"] == game().state["metrics"]


def test_live_superior_reaction_controls_delayed_trigger_without_deciding_outcome() -> None:
    current = game()
    reaction = SuperiorReaction(
        immediate_reply="材料已收，请等待进一步安排。",
        reaction_kind="conditional_follow_up",
        condition="就业数字仍未核实",
        delay_days=4,
        expires_after_days=20,
        proposed_action="补报就业数据来源和责任节点。",
    )
    current = submit_document(
        current,
        idempotency_key="agent-superior-reaction",
        document_id="doc-environment",
        recipient_id="superior",
        cover_note="请审阅。",
        superior_reaction=reaction,
    )
    trigger = current.state["delayed_triggers"][0]
    assert trigger["due_date"] == "2026-09-05"
    assert trigger["detail"] == "补报就业数据来源和责任节点。"
    assert current.state["metrics"] == game().state["metrics"]
