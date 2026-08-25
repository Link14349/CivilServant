import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from .config import PROMPT_DIR
from .models import ParsedAction, ParsedConversation
from .scenario import ACTORS, actor_agent_context, allowed_tags, option_by_id, turn_definition


class LlmError(RuntimeError):
    pass


class DeepSeekProvider:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.system_prompt = _read_prompt(PROMPT_DIR / "turn_agent.md")
        self.conversation_prompt = _read_prompt(PROMPT_DIR / "conversation_agent.md")

    def validate(self, api_key: str, api_base: str, model: str) -> None:
        base = validate_api_base(api_base)
        try:
            response = httpx.get(
                "{}/models".format(base),
                headers={"Authorization": "Bearer {}".format(api_key)},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise LlmError("无法连接模型服务，请检查 API Base URL 和网络。") from exc

        if response.status_code == 401:
            raise LlmError("API Key 无效或没有访问权限。")
        if response.status_code >= 400:
            raise LlmError("模型服务返回错误（HTTP {}）。".format(response.status_code))
        try:
            model_ids = {item["id"] for item in response.json().get("data", [])}
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError("模型服务返回了无法识别的模型列表。") from exc
        if model not in model_ids:
            raise LlmError("模型列表中没有 {}，请检查模型名。".format(model))

    def resolve_action(
        self,
        api_key: str,
        game: Any,
        option_id: Optional[str],
        custom_text: Optional[str],
    ) -> ParsedAction:
        base = validate_api_base(game.api_base)
        turn = turn_definition(game.turn_index, game.state)
        fixed_tag = option_id or ""
        if option_id:
            option = option_by_id(game.turn_index, option_id)
            player_action = option["directive"]
        else:
            player_action = (custom_text or "").strip()

        actor_payload: Dict[str, Dict[str, str]] = {}
        for actor_id in turn["actor_ids"]:
            actor_payload[actor_id] = {
                "name": ACTORS[actor_id]["name"],
                "title": ACTORS[actor_id]["title"],
                "public_position": ACTORS[actor_id]["public_position"],
            }

        user_payload = {
            "instruction": "请以 JSON 格式解析本回合行动并生成即时反应。",
            "turn_number": game.turn_index + 1,
            "turn_title": turn["title"],
            "briefing": turn["briefing"],
            "player_action": player_action,
            "fixed_strategy_tag": fixed_tag,
            "allowed_strategy_tags": allowed_tags(game.turn_index),
            "relevant_actors": actor_payload,
            "recent_history": [
                {
                    "turn": item["turn"],
                    "directive_summary": item["directive_summary"],
                }
                for item in game.history[-2:]
            ],
        }
        request_body = {
            "model": game.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.35,
            "max_tokens": 900,
            "stream": False,
        }
        try:
            response = httpx.post(
                "{}/chat/completions".format(base),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LlmError("DeepSeek 响应超时，本回合尚未提交，可以重试。") from exc
        except httpx.HTTPError as exc:
            raise LlmError("无法连接 DeepSeek，本回合尚未提交。") from exc

        if response.status_code == 401:
            raise LlmError("API Key 已失效，请重新输入。")
        if response.status_code >= 400:
            raise LlmError("DeepSeek 返回错误（HTTP {}），本回合尚未提交。".format(response.status_code))

        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            parsed = ParsedAction.model_validate(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError("DeepSeek 没有返回可用的结构化行动，本回合尚未提交。") from exc

        valid_tags = allowed_tags(game.turn_index)
        if fixed_tag:
            parsed.strategy_tag = fixed_tag
        elif parsed.strategy_tag not in valid_tags:
            raise LlmError("DeepSeek 对自由输入的分类超出本回合规则，请换一种表述。")

        valid_actor_ids = set(turn["actor_ids"])
        parsed.npc_reactions = [
            reaction
            for reaction in parsed.npc_reactions[:2]
            if reaction.get("actor_id") in valid_actor_ids and reaction.get("text")
        ]
        return parsed

    def resolve_conversation(
        self,
        api_key: str,
        game: Any,
        actor_id: str,
        channel: str,
        intent: str,
        message: str,
    ) -> ParsedConversation:
        base = validate_api_base(game.api_base)
        turn = turn_definition(game.turn_index, game.state)
        actor_context = actor_agent_context(actor_id)
        actor_context["relationship_to_player"] = _relationship_band(
            int(game.state["relations"][actor_id])
        )
        recent_conversations = [
            {
                "turn": item["turn"],
                "channel": item["channel"],
                "player_message": item["player_message"],
                "reply": item["reply"],
            }
            for item in game.state.get("conversations", [])
            if item["actor_id"] == actor_id
        ][-4:]
        user_payload = {
            "instruction": "只以当前人物身份回应这次谈话，并返回 JSON。",
            "turn": {
                "number": game.turn_index + 1,
                "title": turn["title"],
                "public_briefing": turn["briefing"],
            },
            "actor": actor_context,
            "visible_reports": [
                {"source": item["source"], "title": item["title"], "summary": item["summary"]}
                for item in turn["reports"]
            ],
            "public_decisions": [
                {
                    "turn": item["turn"],
                    "directive_summary": item["directive_summary"],
                    "responsibility": item.get("responsibility"),
                }
                for item in game.history[-3:]
            ],
            "recent_direct_conversations": recent_conversations,
            "direct_private_records": [
                item
                for item in game.state.get("private_records", [])
                if item["actor_id"] == actor_id
            ][-4:],
            "channel": channel,
            "intent": intent,
            "player_message": message,
        }
        request_body = {
            "model": game.model,
            "messages": [
                {"role": "system", "content": self.conversation_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.45,
            "max_tokens": 850,
            "stream": False,
        }
        try:
            response = httpx.post(
                "{}/chat/completions".format(base),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LlmError("人物回应超时，会谈时段尚未扣除，可以重试。") from exc
        except httpx.HTTPError as exc:
            raise LlmError("无法连接 DeepSeek，会谈尚未提交。") from exc

        if response.status_code == 401:
            raise LlmError("API Key 已失效，请重新输入。")
        if response.status_code >= 400:
            raise LlmError("DeepSeek 返回错误（HTTP {}），会谈尚未提交。".format(response.status_code))
        try:
            content = response.json()["choices"][0]["message"]["content"]
            parsed = ParsedConversation.model_validate(json.loads(content))
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError("人物 Agent 没有返回可用的结构化回应，会谈尚未提交。") from exc

        allowed_beliefs = {item["id"] for item in actor_context["beliefs"]}
        if not set(parsed.used_belief_ids).issubset(allowed_beliefs):
            raise LlmError("人物 Agent 引用了其认知范围外的信息，会谈已拒绝提交。")
        return parsed


def validate_api_base(api_base: str) -> str:
    base = api_base.strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme == "https" and parsed.netloc:
        return base
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return base
    raise LlmError("API Base URL 必须使用 HTTPS；本地模型可使用 localhost HTTP。")


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _relationship_band(value: int) -> str:
    if value >= 66:
        return "信任较高，愿意主动提供坏消息"
    if value >= 53:
        return "合作积极，但仍会保护职责边界"
    if value >= 43:
        return "仍在观察玩家风格"
    if value >= 32:
        return "有所保留，倾向采用正式口径"
    return "关系紧张，优先自保并减少非必要披露"
