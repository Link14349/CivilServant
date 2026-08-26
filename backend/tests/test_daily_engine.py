import pytest

from civilservant.daily_engine import (
    add_meeting_materials,
    actor_agent_projection,
    actor_available_knowledge_ids,
    add_conversation_reply,
    add_player_speech,
    begin_conversation_generation,
    begin_meeting_generation,
    close_day,
    close_scene,
    commit_conversation_reply,
    commit_meeting_speech,
    create_daily_game,
    create_document_task,
    create_notebook_note,
    hydrate_daily_actor_state,
    schedule_calendar_entry,
    set_meeting_discussion_mode,
    start_conversation,
    start_field_visit,
    start_meeting,
    submit_document,
    template_conversation_utterance,
    template_meeting_utterance,
    to_daily_game_view,
    update_notebook_note,
)
from civilservant.daily_agent_tools import execute_agent_tool
from civilservant.daily_models import AgentToolCall, PostSceneResult, SuperiorReaction
from civilservant.daily_scenario import ACTORS, PUBLIC_REFERENCE_MATERIALS


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


def test_scheduled_meeting_keeps_selected_material_version_until_start() -> None:
    current = schedule_calendar_entry(
        game(),
        idempotency_key="schedule-meeting-files",
        target_date="2026-09-02",
        kind="meeting",
        title="北山材料核对会",
        participant_ids=["mayor", "county_secretary"],
        location_id=None,
        meeting_type="coordination",
        discussion_mode="chaired",
        meeting_document_ids=["doc-county-request"],
        notified=True,
    )
    scheduled = next(
        item for item in current.state["calendar"] if item["title"] == "北山材料核对会"
    )
    selected_content = scheduled["meeting_materials"][0]["content"]
    next(
        item for item in current.state["documents"] if item["id"] == "doc-county-request"
    )["content"] = "预约后形成的新版本内容"
    current = close_day(current, idempotency_key="close-day-before-scheduled-meeting")
    scene = current.state["active_scene"]
    assert scene["kind"] == "meeting"
    assert scene["meeting_materials"][0]["content"] == selected_content
    assert "会前材料已向全体与会者发放" in scene["transcript"][0]["text"]


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


def test_meeting_materials_are_versioned_and_visible_only_to_attendees() -> None:
    current = start_meeting(
        game(),
        idempotency_key="start-meeting-with-files",
        meeting_type="symposium",
        discussion_mode="chaired",
        title="北山材料核对会",
        agenda="逐项核对就业和整改口径",
        participant_ids=["mayor", "county_secretary"],
        meeting_document_ids=["doc-environment", "doc-county-request"],
    )
    scene = current.state["active_scene"]
    assert [item["document_id"] for item in scene["meeting_materials"]] == [
        "doc-environment",
        "doc-county-request",
    ]
    assert all(
        set(item["audience_ids"]) == {"player", "mayor", "county_secretary"}
        for item in scene["meeting_materials"]
    )
    assert "doc-environment" in {
        item["id"] for item in actor_agent_projection(current, "mayor")["visible_documents"]
    }
    assert "doc-environment" not in {
        item["id"] for item in actor_agent_projection(current, "banker")["visible_documents"]
    }

    original_snapshot = scene["meeting_materials"][0]["content"]
    next(item for item in current.state["documents"] if item["id"] == "doc-environment")["content"] = "会后形成的新内容"
    mayor_projection = actor_agent_projection(current, "mayor")
    assert next(
        item for item in mayor_projection["visible_documents"] if item["id"] == "doc-environment"
    )["version"] == scene["meeting_materials"][0]["document_version"]
    assert scene["meeting_materials"][0]["content"] == original_snapshot
    tool_result, _ = execute_agent_tool(
        current,
        "mayor",
        "utterance",
        AgentToolCall(call_id="read-meeting-file", name="read_file", arguments={"document_id": "doc-environment"}),
        [],
    )
    assert tool_result["data"]["content"] == original_snapshot


def test_player_can_send_additional_file_during_meeting() -> None:
    current = start_meeting(
        game(),
        idempotency_key="start-meeting-before-extra-file",
        meeting_type="coordination",
        discussion_mode="chaired",
        title="防汛协调会",
        agenda="核对险段与物资准备",
        participant_ids=["mayor", "water_director"],
        meeting_document_ids=["doc-flood"],
    )
    previous_record_version = current.state["active_scene"]["record_version"]
    current = add_meeting_materials(
        current,
        idempotency_key="send-extra-file",
        record_version=previous_record_version,
        document_ids=["doc-fiscal-note"],
    )
    scene = current.state["active_scene"]
    extra = next(
        item for item in scene["meeting_materials"] if item["document_id"] == "doc-fiscal-note"
    )
    assert extra["distribution_kind"] == "during_meeting"
    assert extra["distributed_record_version"] == previous_record_version + 1
    assert scene["record_version"] == previous_record_version + 1
    assert "临时向全体与会者发送" in scene["transcript"][-1]["text"]
    assert "doc-fiscal-note" in {
        item["id"] for item in actor_agent_projection(current, "water_director")["visible_documents"]
    }

    with pytest.raises(ValueError, match="已经发给"):
        add_meeting_materials(
            current,
            idempotency_key="send-same-extra-file",
            record_version=scene["record_version"],
            document_ids=["doc-fiscal-note"],
        )


def test_player_can_switch_discussion_mode_during_meeting() -> None:
    current = start_meeting(
        game(),
        idempotency_key="start-meeting-mode-switch",
        meeting_type="symposium",
        discussion_mode="chaired",
        title="北山产业座谈会",
        agenda="核实就业和资产条件",
        participant_ids=["mayor", "county_secretary"],
    )
    scene = current.state["active_scene"]
    previous_record_version = scene["record_version"]
    current = set_meeting_discussion_mode(
        current,
        idempotency_key="switch-to-free",
        record_version=previous_record_version,
        discussion_mode="free",
    )
    scene = current.state["active_scene"]
    assert scene["discussion_mode"] == "free"
    assert scene["record_version"] == previous_record_version + 1
    assert "自由磋商" in scene["transcript"][-1]["text"]
    # free mode no longer requires a nomination; it picks a speaker or falls silent
    current, selected = begin_meeting_generation(
        current,
        idempotency_key="free-round",
        record_version=scene["record_version"],
        nominated_actor_id=None,
    )
    assert selected is None or selected in {"mayor", "county_secretary"}


def test_cannot_switch_discussion_mode_while_speech_is_generating() -> None:
    current = start_meeting(
        game(),
        idempotency_key="start-meeting-locked-switch",
        meeting_type="symposium",
        discussion_mode="chaired",
        title="北山产业座谈会",
        agenda="核实就业和资产条件",
        participant_ids=["mayor", "county_secretary"],
    )
    scene = current.state["active_scene"]
    current, _ = begin_meeting_generation(
        current,
        idempotency_key="nominate-mayor",
        record_version=scene["record_version"],
        nominated_actor_id="mayor",
    )
    scene = current.state["active_scene"]
    assert scene["generation"]["status"] == "thinking"
    with pytest.raises(ValueError, match="生成"):
        set_meeting_discussion_mode(
            current,
            idempotency_key="switch-during-thinking",
            record_version=scene["record_version"],
            discussion_mode="free",
        )


def test_available_knowledge_includes_own_commitments_memories_tasks_and_records() -> None:
    current = game()
    state = current.state
    state.setdefault("commitments", []).append(
        {
            "id": "commitment-146",
            "summary": "水利局会同南川区明天提交修改后的正式稿",
            "giver_id": "secretary_general",
            "receiver_id": "water_director",
            "known_by_ids": ["secretary_general", "water_director"],
            "status": "active",
        }
    )
    state["actor_runtime"]["secretary_general"]["memories"].append(
        {"id": "memory-3", "summary": "上次谈话提到资金缺口", "importance": 3}
    )
    state["actor_runtime"]["secretary_general"]["tasks"].append(
        {"id": "todo-9", "summary": "跟进险段复核", "status": "planned"}
    )
    state.setdefault("scene_archive", []).append(
        {
            "id": "scene-7",
            "kind": "meeting",
            "participants": [{"actor_id": "secretary_general"}, {"actor_id": "mayor"}],
            "title": "上次协调会",
            "transcript": [{"id": "turn-77", "speaker_id": "mayor", "text": "资金要核实。"}],
            "meeting_materials": [],
        }
    )
    state["documents"].append(
        {
            "id": "doc-for-sg",
            "version": 1,
            "title": "复核纪要",
            "document_type": "report",
            "author_id": "water_director",
            "author_label": "水务局",
            "status": "received",
            "confidentiality": "内部",
            "created_date": state["current_date"],
            "due_date": None,
            "summary": "纪要",
            "content": "正文",
            "recipient_ids": ["secretary_general"],
            "source_document_ids": ["doc-county-request"],
            "formal_effect": "供参考",
            "annotations": [],
        }
    )
    allowed = set(actor_available_knowledge_ids(current, "secretary_general"))
    # 本人承诺/记忆/待办/亲历场景记录/转写轮次/实体引用/文件引用来源都应放行
    assert {
        "commitment-146",
        "memory-3",
        "todo-9",
        "scene-7",
        "turn-77",
        "mayor",
        "water_director",
        "system",
        "secretary_general",
        "doc-for-sg",
        "doc-county-request",
    }.issubset(allowed)
    # 角色私有的承诺/记忆/文件及其引用来源不应进入其他人的允许集合
    mayor_allowed = set(actor_available_knowledge_ids(current, "mayor"))
    assert "commitment-146" not in mayor_allowed
    assert "memory-3" not in mayor_allowed
    assert "doc-for-sg" not in mayor_allowed
    assert "doc-county-request" not in mayor_allowed


def test_player_cannot_distribute_a_document_they_cannot_access() -> None:
    current = game()
    current.state["documents"].append(
        {
            "id": "private-mayor-note",
            "version": 1,
            "title": "市长个人工作便笺",
            "document_type": "note",
            "author_id": "mayor",
            "status": "draft",
            "confidentiality": "个人",
            "created_date": current.state["current_date"],
            "due_date": None,
            "summary": "玩家无权读取。",
            "content": "不得通过会议材料接口越权发送。",
            "recipient_ids": ["mayor"],
            "source_document_ids": [],
            "formal_effect": "个人便笺。",
            "annotations": [],
            "handled_date": None,
        }
    )
    with pytest.raises(ValueError, match="无权"):
        start_meeting(
            current,
            idempotency_key="start-with-private-file",
            meeting_type="coordination",
            discussion_mode="chaired",
            title="越权材料测试会",
            agenda="验证文件权限",
            participant_ids=["mayor"],
            meeting_document_ids=["private-mayor-note"],
        )


def test_conversation_generation_uses_record_lease_and_player_can_cancel() -> None:
    current = start_conversation(
        game(),
        idempotency_key="start-streaming-talk",
        actor_id="mayor",
        channel="private_meeting",
    )
    current = add_player_speech(
        current,
        idempotency_key="ask-streaming-talk",
        record_version=current.state["active_scene"]["record_version"],
        text="请先说明财政边界。",
    )
    current, actor_id = begin_conversation_generation(current)
    generation_id = current.state["active_scene"]["generation"]["id"]
    assert actor_id == "mayor"
    current = add_player_speech(
        current,
        idempotency_key="interrupt-streaming-talk",
        record_version=current.state["active_scene"]["record_version"],
        text="先等等，我补充一个条件。",
    )
    assert current.state["active_scene"]["generation"]["status"] == "canceled"
    try:
        commit_conversation_reply(
            current,
            generation_id=generation_id,
            actor_id=actor_id,
            utterance=template_conversation_utterance(current, actor_id, "请说明。"),
        )
    except ValueError as exc:
        assert "失效" in str(exc)
    else:
        raise AssertionError("取消的谈话回应不应能够提交")


def test_conversation_activity_keeps_only_event_level_summary() -> None:
    current = start_conversation(
        game(),
        idempotency_key="start-private-summary-talk",
        actor_id="mayor",
        channel="private_meeting",
    )
    current = add_player_speech(
        current,
        idempotency_key="private-summary-speech",
        record_version=current.state["active_scene"]["record_version"],
        text="这句具体谈话不应出现在工作记录里。",
    )
    current = close_scene(
        current,
        idempotency_key="close-private-summary-talk",
        record_version=current.state["active_scene"]["record_version"],
    )
    activity = to_daily_game_view(current).activity
    assert any(item.title == "与周立衡进行了面谈" for item in activity)
    assert "这句具体谈话" not in "".join(
        "{}{}".format(item.title, item.summary) for item in activity
    )


def test_legacy_conversation_activity_is_folded_for_player_view() -> None:
    current = game()
    current.state["activity"].extend(
        [
            {
                "id": "legacy-start",
                "date": "2026-09-01",
                "kind": "conversation",
                "title": "与周立衡面谈",
                "summary": "面谈已经开始。",
                "visible": True,
            },
            {
                "id": "legacy-speech",
                "date": "2026-09-01",
                "kind": "speech",
                "title": "玩家发言",
                "summary": "旧版具体发言",
                "visible": True,
            },
            {
                "id": "legacy-close",
                "date": "2026-09-01",
                "kind": "scene_closed",
                "title": "与周立衡面谈结束",
                "summary": "场景记录已经冻结。",
                "visible": True,
            },
        ]
    )
    activity = to_daily_game_view(current).activity
    assert len(activity) == 1
    assert activity[0].title == "与周立衡进行了面谈"
    assert activity[0].summary == ""


def test_player_notebook_is_private_editable_and_costs_no_action_points() -> None:
    current = game()
    original_points = current.state["action_remaining"]
    current = create_notebook_note(
        current,
        idempotency_key="create-private-note",
        title="财政核实",
        content="只有玩家知道的待核问题。",
    )
    note = current.state["notebook_notes"][0]
    assert current.state["action_remaining"] == original_points
    assert to_daily_game_view(current).notebook_notes[0].content == "只有玩家知道的待核问题。"
    assert "只有玩家知道的待核问题" not in str(actor_agent_projection(current, "mayor"))

    current = update_notebook_note(
        current,
        idempotency_key="update-private-note",
        note_id=note["id"],
        operation="update",
        content="已经核实，仍需追问附件。",
    )
    assert current.state["notebook_notes"][0]["content"] == "已经核实，仍需追问附件。"
    current = update_notebook_note(
        current,
        idempotency_key="delete-private-note",
        note_id=note["id"],
        operation="delete",
    )
    assert current.state["notebook_notes"] == []
    assert current.state["action_remaining"] == original_points


def test_actor_projection_does_not_contain_other_private_beliefs() -> None:
    projection = actor_agent_projection(game(), "mayor")
    serialized = str(projection)
    assert "mayor_cash_crisis" in serialized
    assert "county_real_jobs" not in serialized
    assert "chairman_collateral_truth" not in serialized
    assert "finance_competing_requests" not in serialized
    assert {item["id"] for item in projection["public_background"]} == {
        item["id"] for item in PUBLIC_REFERENCE_MATERIALS
    }


def test_existing_save_hydrates_new_directory_actors_without_leaking_beliefs() -> None:
    current = game()
    original_version = current.version
    for actor_id in ["nanchuan_secretary", "finance_director", "linjiang_secretary"]:
        current.state["relations"].pop(actor_id)
        current.state["actor_runtime"].pop(actor_id)

    hydrated = hydrate_daily_actor_state(current)
    assert hydrated.version == original_version
    assert hydrated.state["relations"]["nanchuan_secretary"] == 50
    assert hydrated.state["relations"]["finance_director"] == 50
    assert hydrated.state["relations"]["linjiang_secretary"] == 50
    actor = next(item for item in to_daily_game_view(hydrated).actors if item.id == "nanchuan_secretary")
    assert actor.title == "南川区委书记"
    assert actor.directory_group == "县区主官"

    projection = actor_agent_projection(hydrated, "nanchuan_secretary")
    serialized = str(projection)
    assert "nanchuan_acceptance_gap" in serialized
    assert "county_real_jobs" not in serialized


def test_public_reference_materials_are_visible_to_every_actor_but_private_beliefs_are_not() -> None:
    expected_public_ids = {item["id"] for item in PUBLIC_REFERENCE_MATERIALS}
    current = game()
    for actor_id in ACTORS:
        projection = actor_agent_projection(current, actor_id)
        assert {item["id"] for item in projection["public_background"]} == expected_public_ids
    finance_projection = str(actor_agent_projection(current, "finance_director"))
    assert "finance_competing_requests" in finance_projection
    assert "water_design_gap" not in finance_projection


def test_public_reference_can_be_used_in_conversation_without_becoming_a_private_reveal() -> None:
    current = start_conversation(
        game(),
        idempotency_key="talk-finance-public-background",
        actor_id="finance_director",
        channel="private_meeting",
    )
    utterance = template_conversation_utterance(current, "finance_director", "先说说全市人口基本情况。")
    assert utterance.used_belief_ids == ["ref-city-society"]
    current = add_conversation_reply(current, utterance=utterance)
    assert "ref-city-society" not in current.state["player_beliefs"]
    assert "三百七十八万" in current.state["active_scene"]["transcript"][-1]["text"]


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
