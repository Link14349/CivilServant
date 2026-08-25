from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import DEFAULT_API_BASE, DEFAULT_MODEL, FRONTEND_DIST
from .engine import (
    apply_action,
    apply_conversation,
    create_game,
    template_action,
    template_conversation,
    to_game_view,
)
from .llm import DeepSeekProvider, LlmError, validate_api_base
from .models import (
    CreateGameRequest,
    GameView,
    SubmitActionRequest,
    SubmitConversationRequest,
    ValidateLlmRequest,
    ValidateLlmResponse,
)
from .scenario import option_by_id, turn_definition
from .store import GameStore


app = FastAPI(title="CivilServant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = GameStore()
provider = DeepSeekProvider()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "default_model": DEFAULT_MODEL}


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
        provider.validate(x_deepseek_api_key, payload.api_base, payload.model)
    except LlmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ValidateLlmResponse(ok=True, model=payload.model, message="连接成功，模型可用。")


@app.post("/api/games", response_model=GameView, status_code=201)
def start_game(payload: CreateGameRequest) -> GameView:
    try:
        api_base = validate_api_base(payload.api_base)
    except LlmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    game = create_game(
        player_name=payload.player_name,
        mode=payload.mode,
        model=payload.model,
        api_base=api_base,
        seed=payload.seed,
    )
    store.create(game)
    return to_game_view(game)


@app.get("/api/games/{game_id}", response_model=GameView)
def load_game(game_id: str) -> GameView:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="没有找到这个存档。")
    return to_game_view(game)


@app.post("/api/games/{game_id}/conversations", response_model=GameView)
def submit_conversation(
    game_id: str,
    payload: SubmitConversationRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> GameView:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="没有找到这个存档。")
    if game.status != "active":
        raise HTTPException(status_code=409, detail="本局已经结束。")
    if payload.version != game.version:
        raise HTTPException(status_code=409, detail="页面状态已经过期，请刷新后重试。")
    if payload.actor_id not in turn_definition(game.turn_index, game.state)["actor_ids"]:
        raise HTTPException(status_code=400, detail="这名人物与当前议题没有直接关系。")
    if int(game.state.get("attention_remaining", 3)) <= 0:
        raise HTTPException(status_code=400, detail="本回合的会谈时段已经用完。")

    if game.mode == "live":
        if not x_deepseek_api_key:
            raise HTTPException(status_code=401, detail="本局需要 DeepSeek API Key。")
        try:
            parsed = provider.resolve_conversation(
                api_key=x_deepseek_api_key,
                game=game,
                actor_id=payload.actor_id,
                channel=payload.channel,
                intent=payload.intent,
                message=payload.message,
            )
        except (LlmError, KeyError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        try:
            parsed = template_conversation(
                game=game,
                actor_id=payload.actor_id,
                channel=payload.channel,
                intent=payload.intent,
                message=payload.message,
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail="没有找到这名人物。") from exc

    try:
        updated = apply_conversation(
            game=game,
            actor_id=payload.actor_id,
            channel=payload.channel,
            intent=payload.intent,
            message=payload.message,
            result=parsed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not store.save(updated, expected_version=game.version):
        raise HTTPException(status_code=409, detail="存档已被其他请求更新，请刷新后重试。")
    return to_game_view(updated)


@app.post("/api/games/{game_id}/actions", response_model=GameView)
def submit_action(
    game_id: str,
    payload: SubmitActionRequest,
    x_deepseek_api_key: Optional[str] = Header(default=None),
) -> GameView:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="没有找到这个存档。")
    if game.status != "active":
        raise HTTPException(status_code=409, detail="本局已经结束。")
    if payload.version != game.version:
        raise HTTPException(status_code=409, detail="页面状态已经过期，请刷新后重试。")

    if payload.option_id:
        try:
            option = option_by_id(game.turn_index, payload.option_id)
            choice = option["label"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail="这个选项不属于当前回合。") from exc
    else:
        custom = (payload.custom_text or "").strip()
        choice = "其他：{}".format(custom if len(custom) <= 34 else custom[:33] + "…")

    if game.mode == "live":
        if not x_deepseek_api_key:
            raise HTTPException(status_code=401, detail="本局需要 DeepSeek API Key。")
        try:
            parsed = provider.resolve_action(
                api_key=x_deepseek_api_key,
                game=game,
                option_id=payload.option_id,
                custom_text=payload.custom_text,
            )
        except LlmError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        parsed, choice = template_action(game, payload.option_id, payload.custom_text)

    try:
        updated = apply_action(game, parsed, choice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not store.save(updated, expected_version=game.version):
        raise HTTPException(status_code=409, detail="存档已被其他请求更新，请刷新后重试。")
    return to_game_view(updated)


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
