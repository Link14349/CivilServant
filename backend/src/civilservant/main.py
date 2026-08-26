from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import DEFAULT_API_BASE, DEFAULT_MODEL, FRONTEND_DIST
from .daily_engine import (
    SCHEMA_VERSION,
    act_on_document,
    add_conversation_reply,
    add_player_speech,
    begin_meeting_generation,
    cancel_calendar_entry,
    close_day,
    close_scene,
    command_was_processed,
    commit_meeting_speech,
    create_daily_game,
    create_document_task,
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
    vote_in_meeting,
)
from .daily_llm import DailyAgentProvider
from .daily_models import (
    CalendarUpdateRequest,
    CloseDayRequest,
    CloseSceneRequest,
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
)
from .llm import DeepSeekProvider, LlmError, validate_api_base
from .models import StoredGame, ValidateLlmRequest, ValidateLlmResponse
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
async def stream_game(game_id: str) -> StreamingResponse:
    _get_game(game_id)

    async def events():
        last_version = -1
        for _ in range(120):
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
            await asyncio.sleep(0.5)
        yield "event: reconnect\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


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
def player_speech(
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
    try:
        updated = add_player_speech(
            game,
            idempotency_key=payload.idempotency_key,
            record_version=payload.record_version,
            text=payload.text,
        )
        if scene["kind"] in {"conversation", "superior_meeting"}:
            actor_id = next(
                item["actor_id"]
                for item in scene["participants"]
                if item["actor_id"] != "player"
            )
            if game.mode == "live":
                utterance = daily_provider.resolve_conversation(
                    api_key=x_deepseek_api_key or "",
                    game=updated,
                    actor_id=actor_id,
                    player_message=payload.text,
                )
            else:
                utterance = template_conversation_utterance(updated, actor_id, payload.text)
            updated = add_conversation_reply(updated, utterance=utterance)
    except (ValueError, LlmError) as exc:
        status = 502 if isinstance(exc, LlmError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    _save(updated, game.version)
    if active_generation_id:
        task = generation_tasks.pop(active_generation_id, None)
        if task:
            task.cancel()
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
                    )
                    for actor_id in actor_ids
                ]
            )
        except LlmError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        post_scene_results = dict(zip(actor_ids, results))
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
        try:
            superior_reaction = await asyncio.to_thread(
                daily_provider.resolve_superior_reaction,
                api_key=x_deepseek_api_key or "",
                game=game,
                document_id=document_id,
                cover_note=payload.cover_note,
            )
        except LlmError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
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


async def _complete_meeting_generation(
    *,
    game_id: str,
    generation_id: str,
    actor_id: str,
    api_key: Optional[str],
) -> None:
    try:
        game = store.get(game_id)
        if game is None or not is_daily_game(game):
            return
        if game.mode == "template":
            await asyncio.sleep(0.85)
            utterance = template_meeting_utterance(game, actor_id)
        else:
            utterance = await asyncio.to_thread(
                daily_provider.resolve_meeting_utterance,
                api_key=api_key or "",
                game=game,
                actor_id=actor_id,
            )
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
            return
        store.save(updated, expected_version=latest.version)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        latest = store.get(game_id)
        if latest is None:
            return
        updated = discard_generation(latest, generation_id, "人物发言生成失败：{}".format(str(exc)))
        if updated.version != latest.version:
            store.save(updated, expected_version=latest.version)
    finally:
        generation_tasks.pop(generation_id, None)


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
