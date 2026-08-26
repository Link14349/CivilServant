from __future__ import annotations

import asyncio
import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import DEFAULT_API_BASE, DEFAULT_MODEL, FRONTEND_DIST
from .daily_engine import (
    SCHEMA_VERSION,
    act_on_document,
    add_meeting_materials,
    add_player_speech,
    begin_conversation_generation,
    begin_meeting_generation,
    cancel_calendar_entry,
    close_day,
    close_scene,
    command_was_processed,
    commit_conversation_reply,
    commit_meeting_speech,
    create_daily_game,
    create_document_task,
    create_notebook_note,
    discard_generation,
    hydrate_daily_actor_state,
    is_daily_game,
    schedule_calendar_entry,
    start_conversation,
    start_field_visit,
    start_meeting,
    submit_document,
    template_conversation_utterance,
    template_meeting_utterance,
    to_daily_game_view,
    update_notebook_note,
    vote_in_meeting,
)
from .daily_llm import AgentGenerationCanceled, DailyAgentProvider
from .daily_models import (
    AddMeetingMaterialsRequest,
    CalendarUpdateRequest,
    CloseDayRequest,
    CloseSceneRequest,
    CreateNotebookNoteRequest,
    CreateDailyGameRequest,
    DailyGameView,
    DocumentActionRequest,
    DraftDocumentRequest,
    FieldVisitRequest,
    GenerateMeetingSpeechRequest,
    MeetingVoteRequest,
    PlayerSpeechRequest,
    ScheduleRequest,
    StartConversationRequest,
    StartMeetingRequest,
    SubmitDocumentRequest,
    UpdateNotebookNoteRequest,
)
from .llm import DeepSeekProvider, LlmError, validate_api_base
from .models import StoredGame, ValidateLlmRequest, ValidateLlmResponse
from .daily_scenario import ACTORS
from .store import GameStore


app = FastAPI(title="CivilServant", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = GameStore()
validation_provider = DeepSeekProvider()
daily_provider = DailyAgentProvider()
generation_tasks: Dict[str, asyncio.Task[None]] = {}
generation_cancel_events: Dict[str, threading.Event] = {}
generation_streams: Dict[str, Dict[str, Any]] = {}
agent_debug_traces: Dict[str, Dict[str, Any]] = {}
generation_stream_lock = threading.Lock()
MAX_AGENT_TRACE_EVENTS = 1024


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "default_model": DEFAULT_MODEL,
        "game_schema_version": SCHEMA_VERSION,
    }


@app.get("/api/config")
def config() -> dict:
    return {"default_model": DEFAULT_MODEL, "default_api_base": DEFAULT_API_BASE}


@app.post("/api/llm/validate", response_model=ValidateLlmResponse)
def validate_llm(
    payload: ValidateLlmRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> ValidateLlmResponse:
    if not x_deepseek_api_key:
        raise HTTPException(status_code=401, detail="请输入 DeepSeek API Key。")
    try:
        validation_provider.validate(x_deepseek_api_key, payload.api_base, payload.model)
    except LlmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ValidateLlmResponse(ok=True, model=payload.model, message="连接成功，模型可用。")


@app.post("/api/games", response_model=DailyGameView, status_code=201)
def start_game(payload: CreateDailyGameRequest) -> DailyGameView:
    try:
        api_base = validate_api_base(payload.api_base)
    except LlmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    game = create_daily_game(
        player_name=payload.player_name,
        background=payload.background,
        mode=payload.mode,
        model=payload.model,
        api_base=api_base,
        seed=payload.seed,
    )
    store.create(game)
    return to_daily_game_view(game)


@app.get("/api/games/{game_id}", response_model=DailyGameView)
def load_game(game_id: str) -> DailyGameView:
    game = _get_game(game_id)
    return to_daily_game_view(game)


@app.get("/api/games/{game_id}/stream")
async def stream_game(game_id: str, debug: bool = False) -> StreamingResponse:
    _get_game(game_id)

    async def events():
        last_version = -1
        last_generation_token: tuple[str, int] = ("", -1)
        last_trace_id = ""
        last_trace_revision = -1
        last_trace_sequence = -1
        for _ in range(1200):
            game = store.get(game_id)
            if game is None:
                yield "event: error\ndata: {}\n\n".format(
                    json.dumps({"detail": "存档已不存在"}, ensure_ascii=False)
                )
                return
            if game.version != last_version and is_daily_game(game):
                last_version = game.version
                payload = to_daily_game_view(game).model_dump_json()
                yield "event: game\ndata: {}\n\n".format(payload)
            with generation_stream_lock:
                stream_snapshot = dict(generation_streams.get(game_id, {}))
                trace_snapshot = deepcopy(agent_debug_traces.get(game_id, {})) if debug else {}
            if stream_snapshot:
                generation_token = (
                    str(stream_snapshot.get("generation_id", "")),
                    int(stream_snapshot.get("revision", -1)),
                )
                if generation_token != last_generation_token:
                    last_generation_token = generation_token
                    yield "event: generation\ndata: {}\n\n".format(
                        json.dumps(stream_snapshot, ensure_ascii=False)
                    )
            if trace_snapshot:
                trace_id = str(trace_snapshot.get("trace_id", ""))
                trace_revision = int(trace_snapshot.get("revision", -1))
                if trace_revision != last_trace_revision or trace_id != last_trace_id:
                    replace = trace_id != last_trace_id
                    if replace:
                        last_trace_sequence = -1
                        trace_payload = trace_snapshot
                    else:
                        trace_payload = {
                            **trace_snapshot,
                            "events": [
                                event
                                for event in trace_snapshot.get("events", [])
                                if int(event.get("sequence", -1)) > last_trace_sequence
                            ],
                        }
                    trace_payload["replace"] = replace
                    last_trace_id = trace_id
                    last_trace_revision = trace_revision
                    if trace_payload.get("events"):
                        last_trace_sequence = max(
                            int(event.get("sequence", -1))
                            for event in trace_payload["events"]
                        )
                    yield "event: agent_trace\ndata: {}\n\n".format(
                        json.dumps(trace_payload, ensure_ascii=False)
                    )
            await asyncio.sleep(0.05)
        yield "event: reconnect\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/games/{game_id}/calendar-entries", response_model=DailyGameView)
def create_calendar_entry(game_id: str, payload: ScheduleRequest) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = schedule_calendar_entry(
            game,
            idempotency_key=payload.idempotency_key,
            target_date=payload.date,
            kind=payload.kind,
            title=payload.title,
            participant_ids=payload.participant_ids,
            location_id=payload.location_id,
            meeting_type=payload.meeting_type,
            discussion_mode=payload.discussion_mode,
            meeting_document_ids=payload.meeting_document_ids,
            notified=payload.notified,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.patch("/api/games/{game_id}/calendar-entries/{entry_id}", response_model=DailyGameView)
def update_calendar_entry(
    game_id: str,
    entry_id: str,
    payload: CalendarUpdateRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = cancel_calendar_entry(
            game,
            idempotency_key=payload.idempotency_key,
            entry_id=entry_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/notebook-notes", response_model=DailyGameView)
def add_notebook_note(
    game_id: str,
    payload: CreateNotebookNoteRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = create_notebook_note(
            game,
            idempotency_key=payload.idempotency_key,
            title=payload.title,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.patch("/api/games/{game_id}/notebook-notes/{note_id}", response_model=DailyGameView)
def edit_notebook_note(
    game_id: str,
    note_id: str,
    payload: UpdateNotebookNoteRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = update_notebook_note(
            game,
            idempotency_key=payload.idempotency_key,
            note_id=note_id,
            operation=payload.operation,
            title=payload.title,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/conversations", response_model=DailyGameView)
def create_conversation(
    game_id: str,
    payload: StartConversationRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = start_conversation(
            game,
            idempotency_key=payload.idempotency_key,
            actor_id=payload.actor_id,
            channel=payload.channel,
            opening=payload.opening,
            superior=payload.actor_id == "superior",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/meetings", response_model=DailyGameView)
def create_meeting(game_id: str, payload: StartMeetingRequest) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = start_meeting(
            game,
            idempotency_key=payload.idempotency_key,
            meeting_type=payload.meeting_type,
            discussion_mode=payload.discussion_mode,
            title=payload.title,
            agenda=payload.agenda,
            participant_ids=payload.participant_ids,
            meeting_document_ids=payload.meeting_document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post(
    "/api/games/{game_id}/scenes/{scene_id}/materials",
    response_model=DailyGameView,
)
def add_scene_materials(
    game_id: str,
    scene_id: str,
    payload: AddMeetingMaterialsRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    _require_scene(game, scene_id)
    try:
        updated = add_meeting_materials(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            document_ids=payload.document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/field-visits", response_model=DailyGameView)
def create_field_visit(game_id: str, payload: FieldVisitRequest) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = start_field_visit(
            game,
            idempotency_key=payload.idempotency_key,
            location_id=payload.location_id,
            notified=payload.notified,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/scenes/{scene_id}/player-speeches", response_model=DailyGameView)
async def player_speech(
    game_id: str,
    scene_id: str,
    payload: PlayerSpeechRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    _require_scene(game, scene_id)
    scene = game.state["active_scene"]
    if scene["kind"] in {"conversation", "superior_meeting"} and game.mode == "live":
        _require_key(x_deepseek_api_key)
    active_generation_id = (
        scene["generation"]["id"]
        if scene["generation"]["status"] == "thinking"
        else None
    )
    reply_actor_id: Optional[str] = None
    try:
        updated = add_player_speech(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            text=payload.text,
        )
        if scene["kind"] in {"conversation", "superior_meeting"}:
            updated, reply_actor_id = begin_conversation_generation(updated)
    except (ValueError, LlmError) as exc:
        status = 502 if isinstance(exc, LlmError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    _save(updated, game.version)
    if active_generation_id:
        _cancel_generation(active_generation_id, "玩家发言使本次生成失效。")
    if reply_actor_id:
        generation_id = updated.state["active_scene"]["generation"]["id"]
        _register_generation_stream(
            game_id,
            generation_id,
            reply_actor_id,
            "conversation_reply",
        )
        task = asyncio.create_task(
            _complete_conversation_generation(
                game_id=game_id,
                generation_id=generation_id,
                actor_id=reply_actor_id,
                player_message=payload.text,
                api_key=x_deepseek_api_key,
            )
        )
        generation_tasks[generation_id] = task
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/scenes/{scene_id}/meeting-speech", response_model=DailyGameView)
async def generate_meeting_speech(
    game_id: str,
    scene_id: str,
    payload: GenerateMeetingSpeechRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    _require_scene(game, scene_id)
    scene = game.state["active_scene"]
    if scene["kind"] != "meeting":
        raise HTTPException(status_code=400, detail="当前不是会议场景。")
    willing_actor_ids = None
    speech_intent_debug: Optional[List[Dict[str, Any]]] = None
    if game.mode == "live" and scene["discussion_mode"] == "free":
        _require_key(x_deepseek_api_key)
        actor_ids = [
            item["actor_id"]
            for item in scene["participants"]
            if item["actor_id"] != "player"
        ]
        try:
            results = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        daily_provider.resolve_speech_intent,
                        api_key=x_deepseek_api_key or "",
                        game=game,
                        actor_id=actor_id,
                    )
                    for actor_id in actor_ids
                ]
            )
        except LlmError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        willing_actor_ids = [
            actor_id
            for actor_id, result in zip(actor_ids, results)
            if result.wants_to_speak
        ]
        speech_intent_debug = [
            {
                "actor_id": actor_id,
                "actor_name": ACTORS[actor_id]["name"],
                "result": result.model_dump(mode="json"),
            }
            for actor_id, result in zip(actor_ids, results)
        ]
    elif game.mode == "live":
        _require_key(x_deepseek_api_key)
    try:
        updated, selected = begin_meeting_generation(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            nominated_actor_id=payload.actor_id,
            willing_actor_ids=willing_actor_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    if selected:
        generation_id = updated.state["active_scene"]["generation"]["id"]
        _register_generation_stream(
            game_id,
            generation_id,
            selected,
            "meeting_utterance",
        )
        if speech_intent_debug is not None:
            _append_agent_trace(
                game_id,
                generation_id,
                {
                    "kind": "speech_intent_batch",
                    "round": 0,
                    "title": "自由磋商发言意愿并行判断",
                    "payload": {
                        "decisions": speech_intent_debug,
                        "selected_actor_id": selected,
                    },
                },
            )
        task = asyncio.create_task(
            _complete_meeting_generation(
                game_id=game_id,
                generation_id=generation_id,
                actor_id=selected,
                api_key=x_deepseek_api_key,
            )
        )
        generation_tasks[generation_id] = task
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/scenes/{scene_id}/vote", response_model=DailyGameView)
def meeting_vote(
    game_id: str,
    scene_id: str,
    payload: MeetingVoteRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    _require_scene(game, scene_id)
    try:
        updated = vote_in_meeting(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            resolution=payload.resolution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/scenes/{scene_id}/close", response_model=DailyGameView)
async def finish_scene(
    game_id: str,
    scene_id: str,
    payload: CloseSceneRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    _require_scene(game, scene_id)
    post_scene_results = None
    if game.mode == "live":
        _require_key(x_deepseek_api_key)
        trace_id = "settlement-{}-{}".format(scene_id, game.version)
        _register_agent_trace(
            game_id,
            trace_id,
            None,
            "场景结算",
            "post_scene_settlement",
        )
        actor_ids = [
            item["actor_id"]
            for item in game.state["active_scene"]["participants"]
            if item["actor_id"] != "player"
        ]
        try:
            results = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        daily_provider.resolve_post_scene,
                        api_key=x_deepseek_api_key or "",
                        game=game,
                        actor_id=actor_id,
                        on_trace=lambda event, current_actor_id=actor_id: _append_agent_trace(
                            game_id,
                            trace_id,
                            {**event, "actor_id": current_actor_id},
                        ),
                    )
                    for actor_id in actor_ids
                ]
            )
        except LlmError as exc:
            _append_agent_trace(
                game_id,
                trace_id,
                {
                    "kind": "agent_error",
                    "round": 0,
                    "title": "场景结算 Agent 失败",
                    "payload": {"message": str(exc)},
                },
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        post_scene_results = dict(zip(actor_ids, results))
        _append_agent_trace(
            game_id,
            trace_id,
            {
                "kind": "batch_complete",
                "round": 0,
                "title": "所有人物的场景结算已完成",
                "payload": {"actor_ids": actor_ids},
            },
        )
    try:
        updated = close_scene(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            resolution=payload.resolution,
            post_scene_results=post_scene_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    _clear_generation_stream(game_id)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/documents/{document_id}/actions", response_model=DailyGameView)
def document_action(
    game_id: str,
    document_id: str,
    payload: DocumentActionRequest,
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = act_on_document(
            game,
            idempotency_key=payload.idempotency_key,
            document_id=document_id,
            operation=payload.operation,
            note=payload.note,
            recipient_id=payload.recipient_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/document-tasks", response_model=DailyGameView)
def draft_document(game_id: str, payload: DraftDocumentRequest) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = create_document_task(
            game,
            idempotency_key=payload.idempotency_key,
            author_id=payload.author_id,
            title=payload.title,
            document_type=payload.document_type,
            instructions=payload.instructions,
            source_document_ids=payload.source_document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/documents/{document_id}/submit", response_model=DailyGameView)
async def send_document(
    game_id: str,
    document_id: str,
    payload: SubmitDocumentRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    superior_reaction = None
    if payload.recipient_id == "superior" and game.mode == "live":
        _require_key(x_deepseek_api_key)
        trace_id = "superior-document-{}-{}".format(document_id, game.version)
        _register_agent_trace(
            game_id,
            trace_id,
            "superior",
            ACTORS["superior"]["name"],
            "superior_document_reaction",
        )
        _append_agent_trace(
            game_id,
            trace_id,
            {
                "kind": "model_request",
                "round": 1,
                "title": "请求上级 Agent 阅读报送材料",
                "payload": {"document_id": document_id, "cover_note": payload.cover_note},
            },
        )
        try:
            superior_reaction = await asyncio.to_thread(
                daily_provider.resolve_superior_reaction,
                api_key=x_deepseek_api_key or "",
                game=game,
                document_id=document_id,
                cover_note=payload.cover_note,
            )
        except LlmError as exc:
            _append_agent_trace(
                game_id,
                trace_id,
                {
                    "kind": "agent_error",
                    "round": 1,
                    "title": "上级 Agent 反应生成失败",
                    "payload": {"message": str(exc)},
                },
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        _append_agent_trace(
            game_id,
            trace_id,
            {
                "kind": "agent_complete",
                "round": 1,
                "title": "上级 Agent 已形成材料反应",
                "payload": {"result": superior_reaction.model_dump(mode="json")},
            },
        )
    try:
        updated = submit_document(
            game,
            idempotency_key=payload.idempotency_key,
            document_id=document_id,
            recipient_id=payload.recipient_id,
            cover_note=payload.cover_note,
            superior_reaction=superior_reaction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


@app.post("/api/games/{game_id}/days/current/close", response_model=DailyGameView)
def finish_day(game_id: str, payload: CloseDayRequest) -> DailyGameView:
    game, existing = _prepare_command(game_id, payload.version, payload.idempotency_key)
    if existing:
        return to_daily_game_view(game)
    try:
        updated = close_day(game, idempotency_key=payload.idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save(updated, game.version)
    return to_daily_game_view(updated)


def _register_generation_stream(
    game_id: str,
    generation_id: str,
    actor_id: str,
    task: str,
) -> None:
    generation_cancel_events[generation_id] = threading.Event()
    with generation_stream_lock:
        generation_streams[game_id] = {
            "generation_id": generation_id,
            "actor_id": actor_id,
            "actor_name": ACTORS[actor_id]["name"],
            "text": "",
            "stage": "正在组织思路…",
            "status": "thinking",
            "revision": 1,
        }
        agent_debug_traces[game_id] = {
            "trace_id": generation_id,
            "actor_id": actor_id,
            "actor_name": ACTORS[actor_id]["name"],
            "task": task,
            "status": "running",
            "revision": 1,
            "dropped_event_count": 0,
            "events": [],
        }


def _register_agent_trace(
    game_id: str,
    trace_id: str,
    actor_id: Optional[str],
    actor_name: str,
    task: str,
) -> None:
    with generation_stream_lock:
        agent_debug_traces[game_id] = {
            "trace_id": trace_id,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "task": task,
            "status": "running",
            "revision": 1,
            "dropped_event_count": 0,
            "events": [],
        }


def _append_agent_trace(
    game_id: str,
    trace_id: str,
    event: Dict[str, Any],
) -> None:
    with generation_stream_lock:
        snapshot = agent_debug_traces.get(game_id)
        if not snapshot or snapshot.get("trace_id") != trace_id:
            return
        events = snapshot.setdefault("events", [])
        sanitized = _sanitize_agent_trace_event(snapshot, event)
        sanitized["sequence"] = int(snapshot.get("revision", 0))
        events.append(sanitized)
        if len(events) > MAX_AGENT_TRACE_EVENTS:
            removed = len(events) - MAX_AGENT_TRACE_EVENTS
            del events[:removed]
            snapshot["dropped_event_count"] = int(snapshot.get("dropped_event_count", 0)) + removed
        kind = sanitized.get("kind")
        if kind == "batch_complete":
            if snapshot.get("status") == "running":
                snapshot["status"] = "completed"
        elif kind == "agent_complete" and snapshot.get("actor_id") is not None:
            if snapshot.get("status") == "running":
                snapshot["status"] = "completed"
        elif kind == "safe_fallback":
            snapshot["status"] = "fallback"
        elif kind in {"agent_error", "protocol_error"}:
            snapshot["status"] = "failed" if kind == "agent_error" else snapshot["status"]
        elif kind == "agent_canceled":
            snapshot["status"] = "canceled"
        snapshot["revision"] = int(snapshot.get("revision", 0)) + 1


def _sanitize_agent_trace_event(snapshot: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = _sanitize_debug_value(event)
    payload = sanitized.get("payload")
    if not isinstance(payload, dict):
        return sanitized
    kind = str(sanitized.get("kind") or "")
    task = str(snapshot.get("task") or "")
    if kind == "model_response":
        raw_calls = payload.get("tool_calls")
        payload = {
            "finish_reason": payload.get("finish_reason"),
            "content_present": bool(payload.get("content")),
            "content_length": len(payload.get("content") or "")
            if isinstance(payload.get("content"), str)
            else 0,
            "tool_calls": [
                _summarize_native_tool_call(item)
                for item in raw_calls
            ] if isinstance(raw_calls, list) else [],
        }
    elif kind == "protocol_error":
        payload = {
            "finish_reason": payload.get("finish_reason"),
            "content_present": bool(payload.get("content")),
            "content_length": len(payload.get("content") or "")
            if isinstance(payload.get("content"), str)
            else 0,
        }
    elif kind == "tool_call":
        arguments = payload.get("arguments")
        payload = {
            "call_id": payload.get("call_id"),
            "name": payload.get("name"),
            "argument_keys": sorted(arguments) if isinstance(arguments, dict) else [],
            "argument_summary": _summarize_tool_arguments(
                str(payload.get("name") or ""), arguments
            ),
            "parse_error": payload.get("parse_error"),
        }
    elif kind == "tool_result":
        payload = {
            "call_id": payload.get("call_id"),
            "name": payload.get("name"),
            "result": _summarize_tool_result(payload.get("result")),
        }
    elif kind in {"agent_complete", "safe_fallback"} and isinstance(payload.get("result"), dict):
        payload = {
            **{key: value for key, value in payload.items() if key != "result"},
            "result": _summarize_agent_result(task, payload["result"]),
        }
    elif kind == "speech_intent_batch":
        decisions = payload.get("decisions")
        payload = {
            "decisions": [
                {
                    "actor_id": item.get("actor_id"),
                    "actor_name": item.get("actor_name"),
                    "wants_to_speak": item.get("result", {}).get("wants_to_speak")
                    if isinstance(item.get("result"), dict)
                    else None,
                    "urgency": item.get("result", {}).get("urgency")
                    if isinstance(item.get("result"), dict)
                    else None,
                }
                for item in decisions
                if isinstance(item, dict)
            ] if isinstance(decisions, list) else [],
            "selected_actor_id": payload.get("selected_actor_id"),
        }
    elif kind == "convergence_guard" and isinstance(payload.get("signature"), str):
        payload = {
            **{key: value for key, value in payload.items() if key != "signature"},
            "tool_name": payload["signature"].split(":", 1)[0],
        }
    sanitized["payload"] = payload
    return sanitized


def _summarize_native_tool_call(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"valid": False}
    function = value.get("function")
    if not isinstance(function, dict):
        return {"call_id": value.get("id"), "valid": False}
    raw_arguments = function.get("arguments")
    argument_keys: List[str] = []
    if isinstance(raw_arguments, dict):
        argument_keys = sorted(str(key) for key in raw_arguments)
    elif isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            argument_keys = sorted(str(key) for key in parsed)
    return {
        "call_id": value.get("id"),
        "name": function.get("name"),
        "argument_keys": argument_keys,
    }


def _summarize_tool_arguments(name: str, arguments: Any) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    summary: Dict[str, Any] = {"field_count": len(arguments)}
    if name == "submit_final_result":
        text = arguments.get("text")
        if isinstance(text, str):
            summary["text_length"] = len(text)
        belief_ids = arguments.get("used_belief_ids")
        if isinstance(belief_ids, list):
            summary["used_belief_id_count"] = len(belief_ids)
    return summary


def _summarize_tool_result(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"valid": False}
    summary: Dict[str, Any] = {
        "ok": value.get("ok"),
        "error": value.get("error"),
    }
    data = value.get("data")
    if isinstance(data, list):
        summary.update({"data_type": "list", "item_count": len(data)})
    elif isinstance(data, dict):
        summary.update({
            "data_type": "object",
            "field_count": len(data),
            "staged": data.get("staged") if isinstance(data.get("staged"), bool) else None,
        })
    elif data is not None:
        summary["data_type"] = type(data).__name__
    return summary


def _summarize_agent_result(task: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if task in {"conversation_reply", "meeting_utterance"}:
        text = result.get("text")
        belief_ids = result.get("used_belief_ids")
        effects = result.get("tool_effects")
        return {
            "text": text if isinstance(text, str) else None,
            "used_belief_id_count": len(belief_ids) if isinstance(belief_ids, list) else 0,
            "tool_effect_count": len(effects) if isinstance(effects, list) else 0,
        }
    if task == "superior_document_reaction":
        return {
            "reaction_kind": result.get("reaction_kind"),
            "immediate_reply_length": len(result.get("immediate_reply") or "")
            if isinstance(result.get("immediate_reply"), str)
            else 0,
        }
    intents = result.get("intents")
    effects = result.get("tool_effects")
    return {
        "result_fields": sorted(str(key) for key in result),
        "intent_count": len(intents) if isinstance(intents, list) else 0,
        "tool_effect_count": len(effects) if isinstance(effects, list) else 0,
    }


def _sanitize_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if str(key).lower() in {"api_key", "authorization", "x-deepseek-api-key"}
            else _sanitize_debug_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_debug_value(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_API_KEY]", value)
    return value


def _update_generation_stream(
    game_id: str,
    generation_id: str,
    *,
    text: Optional[str] = None,
    stage: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    with generation_stream_lock:
        snapshot = generation_streams.get(game_id)
        if not snapshot or snapshot.get("generation_id") != generation_id:
            return
        if snapshot.get("status") == "canceled" and status != "canceled":
            return
        if text is not None:
            snapshot["text"] = text
            if status is None:
                snapshot["status"] = "streaming"
        if stage is not None:
            snapshot["stage"] = stage
        if status is not None:
            snapshot["status"] = status
        snapshot["revision"] = int(snapshot.get("revision", 0)) + 1


def _cancel_generation(generation_id: str, message: str) -> None:
    cancel_event = generation_cancel_events.get(generation_id)
    if cancel_event:
        cancel_event.set()
    with generation_stream_lock:
        canceled_game_id: Optional[str] = None
        for current_game_id, snapshot in generation_streams.items():
            if snapshot.get("generation_id") == generation_id:
                snapshot["status"] = "canceled"
                snapshot["stage"] = message
                snapshot["revision"] = int(snapshot.get("revision", 0)) + 1
                canceled_game_id = current_game_id
                break
    if canceled_game_id:
        _append_agent_trace(
            canceled_game_id,
            generation_id,
            {
                "kind": "agent_canceled",
                "round": 0,
                "title": "玩家中断了人物生成",
                "payload": {"message": message},
            },
        )
    task = generation_tasks.pop(generation_id, None)
    if task:
        task.cancel()


def _clear_generation_stream(game_id: str) -> None:
    with generation_stream_lock:
        generation_streams.pop(game_id, None)


async def _stream_template_utterance(
    game_id: str,
    generation_id: str,
    text: str,
    cancel_event: threading.Event,
) -> None:
    visible = ""
    for character in text:
        if cancel_event.is_set():
            raise AgentGenerationCanceled("人物发言已被玩家打断。")
        visible += character
        _update_generation_stream(
            game_id,
            generation_id,
            text=visible,
            stage="正在发言…",
            status="streaming",
        )
        await asyncio.sleep(0.018)


async def _complete_conversation_generation(
    *,
    game_id: str,
    generation_id: str,
    actor_id: str,
    player_message: str,
    api_key: Optional[str],
) -> None:
    cancel_event = generation_cancel_events[generation_id]
    try:
        game = store.get(game_id)
        if game is None or not is_daily_game(game):
            return
        if game.mode == "template":
            _append_agent_trace(
                game_id,
                generation_id,
                {
                    "kind": "template_stub",
                    "round": 0,
                    "title": "模板模式直接生成确定性人物回应",
                    "payload": {"actor_id": actor_id},
                },
            )
            utterance = template_conversation_utterance(game, actor_id, player_message)
            await _stream_template_utterance(
                game_id,
                generation_id,
                utterance.text,
                cancel_event,
            )
        else:
            utterance = await asyncio.to_thread(
                daily_provider.resolve_conversation,
                api_key=api_key or "",
                game=game,
                actor_id=actor_id,
                player_message=player_message,
                on_text_update=lambda text: _update_generation_stream(
                    game_id,
                    generation_id,
                    text=text,
                    stage="正在发言…",
                ),
                on_status=lambda stage: _update_generation_stream(
                    game_id,
                    generation_id,
                    stage=stage,
                ),
                is_cancelled=cancel_event.is_set,
                on_trace=lambda event: _append_agent_trace(
                    game_id,
                    generation_id,
                    event,
                ),
            )
        if cancel_event.is_set():
            return
        latest = store.get(game_id)
        if latest is None:
            return
        try:
            updated = commit_conversation_reply(
                latest,
                generation_id=generation_id,
                actor_id=actor_id,
                utterance=utterance,
            )
        except ValueError:
            _update_generation_stream(
                game_id,
                generation_id,
                stage="谈话记录已经变化，本次回应未写入记录。",
                status="canceled",
            )
            return
        if store.save(updated, expected_version=latest.version):
            _update_generation_stream(
                game_id,
                generation_id,
                text=utterance.text,
                stage="回应已写入谈话记录。",
                status="completed",
            )
            if game.mode == "template":
                _append_agent_trace(
                    game_id,
                    generation_id,
                    {
                        "kind": "agent_complete",
                        "round": 1,
                        "title": "模板人物回应已写入谈话记录",
                        "payload": {"text": utterance.text},
                    },
                )
        else:
            _update_generation_stream(
                game_id,
                generation_id,
                stage="谈话记录已经变化，本次回应未写入记录。",
                status="canceled",
            )
    except (asyncio.CancelledError, AgentGenerationCanceled):
        return
    except Exception as exc:
        await _discard_failed_generation(game_id, generation_id, exc)
    finally:
        generation_tasks.pop(generation_id, None)
        generation_cancel_events.pop(generation_id, None)


async def _complete_meeting_generation(
    *,
    game_id: str,
    generation_id: str,
    actor_id: str,
    api_key: Optional[str],
) -> None:
    cancel_event = generation_cancel_events[generation_id]
    try:
        game = store.get(game_id)
        if game is None or not is_daily_game(game):
            return
        if game.mode == "template":
            _append_agent_trace(
                game_id,
                generation_id,
                {
                    "kind": "template_stub",
                    "round": 0,
                    "title": "模板模式直接生成确定性会议发言",
                    "payload": {"actor_id": actor_id},
                },
            )
            utterance = template_meeting_utterance(game, actor_id)
            await _stream_template_utterance(
                game_id,
                generation_id,
                utterance.text,
                cancel_event,
            )
        else:
            utterance = await asyncio.to_thread(
                daily_provider.resolve_meeting_utterance,
                api_key=api_key or "",
                game=game,
                actor_id=actor_id,
                on_text_update=lambda text: _update_generation_stream(
                    game_id,
                    generation_id,
                    text=text,
                    stage="正在发言…",
                ),
                on_status=lambda stage: _update_generation_stream(
                    game_id,
                    generation_id,
                    stage=stage,
                ),
                is_cancelled=cancel_event.is_set,
                on_trace=lambda event: _append_agent_trace(
                    game_id,
                    generation_id,
                    event,
                ),
            )
        if cancel_event.is_set():
            return
        latest = store.get(game_id)
        if latest is None:
            return
        try:
            updated = commit_meeting_speech(
                latest,
                generation_id=generation_id,
                actor_id=actor_id,
                utterance=utterance,
            )
        except ValueError:
            _update_generation_stream(
                game_id,
                generation_id,
                stage="会议记录已经变化，本次发言未写入记录。",
                status="canceled",
            )
            return
        if store.save(updated, expected_version=latest.version):
            _update_generation_stream(
                game_id,
                generation_id,
                text=utterance.text,
                stage="发言已写入会议记录。",
                status="completed",
            )
            if game.mode == "template":
                _append_agent_trace(
                    game_id,
                    generation_id,
                    {
                        "kind": "agent_complete",
                        "round": 1,
                        "title": "模板人物发言已写入会议记录",
                        "payload": {"text": utterance.text},
                    },
                )
        else:
            _update_generation_stream(
                game_id,
                generation_id,
                stage="会议记录已经变化，本次发言未写入记录。",
                status="canceled",
            )
    except (asyncio.CancelledError, AgentGenerationCanceled):
        return
    except Exception as exc:
        await _discard_failed_generation(game_id, generation_id, exc)
    finally:
        generation_tasks.pop(generation_id, None)
        generation_cancel_events.pop(generation_id, None)


async def _discard_failed_generation(
    game_id: str,
    generation_id: str,
    exc: Exception,
) -> None:
    message = "人物发言生成失败：{}".format(str(exc))
    _append_agent_trace(
        game_id,
        generation_id,
        {
            "kind": "agent_error",
            "round": 0,
            "title": "人物 Agent 生成失败",
            "payload": {"error_type": type(exc).__name__, "message": str(exc)},
        },
    )
    _update_generation_stream(
        game_id,
        generation_id,
        stage=message,
        status="failed",
    )
    latest = store.get(game_id)
    if latest is None:
        return
    updated = discard_generation(latest, generation_id, message)
    if updated.version != latest.version:
        store.save(updated, expected_version=latest.version)


def _get_game(game_id: str) -> StoredGame:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="没有找到这个存档。")
    if not is_daily_game(game):
        raise HTTPException(status_code=409, detail="这是旧版六回合存档，请新建逐日模拟存档。")
    return hydrate_daily_actor_state(game)


def _prepare_command(game_id: str, version: int, key: str) -> tuple[StoredGame, bool]:
    game = _get_game(game_id)
    if command_was_processed(game, key):
        return game, True
    if version != game.version:
        raise HTTPException(status_code=409, detail="页面状态已经过期，请刷新后重试。")
    return game, False


def _require_scene(game: StoredGame, scene_id: str) -> None:
    scene = game.state.get("active_scene")
    if not scene or scene["id"] != scene_id:
        raise HTTPException(status_code=409, detail="这个互动场景已经结束或被其他日程替代。")


def _require_key(key: Optional[str]) -> None:
    if not key:
        raise HTTPException(status_code=401, detail="本局需要 DeepSeek API Key。")


def _save(game: StoredGame, expected_version: int) -> None:
    if not store.save(game, expected_version=expected_version):
        raise HTTPException(status_code=409, detail="存档已被其他请求更新，请刷新后重试。")


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        dist_root = FRONTEND_DIST.resolve()
        candidate = (dist_root / full_path).resolve()
        try:
            candidate.relative_to(dist_root)
            inside_dist = True
        except ValueError:
            inside_dist = False
        if full_path and inside_dist and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist_root / "index.html")
