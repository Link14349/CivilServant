from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import httpx

from .config import PROMPT_DIR
from .daily_engine import actor_agent_projection
from .daily_models import AgentUtterance, PostSceneResult, SpeechIntent, SuperiorReaction
from .daily_scenario import actor_knowledge_ids
from .llm import LlmError, validate_api_base
from .models import StoredGame


class DailyAgentProvider:
    def __init__(self, timeout_seconds: float = 35.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.system_prompt = _read_prompt(PROMPT_DIR / "daily_actor.md")

    def resolve_conversation(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
        player_message: str,
    ) -> AgentUtterance:
        payload = {
            "task": "conversation_reply",
            "instruction": "以当前人物身份直接回应玩家，返回 text 与 used_belief_ids。",
            "context": actor_agent_projection(game, actor_id),
            "player_message": player_message,
            "output_schema": {
                "text": "string",
                "used_belief_ids": ["belief_id"],
            },
        }
        result = AgentUtterance.model_validate(self._request(api_key, game, payload, 900))
        self._validate_beliefs(actor_id, result)
        return result

    def resolve_meeting_utterance(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> AgentUtterance:
        payload = {
            "task": "meeting_utterance",
            "instruction": "你已经获得发言权。结合当前会议记录作一段简洁、有职务立场的发言。",
            "context": actor_agent_projection(game, actor_id),
            "output_schema": {
                "text": "string",
                "used_belief_ids": ["belief_id"],
            },
        }
        result = AgentUtterance.model_validate(self._request(api_key, game, payload, 1000))
        self._validate_beliefs(actor_id, result)
        return result

    def resolve_speech_intent(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> SpeechIntent:
        payload = {
            "task": "speech_intent",
            "instruction": (
                "只判断此刻是否希望发言。考虑自己是否有新信息、是否需要回应、职务责任、"
                "刚刚是否已经发言以及沉默是否更符合人物利益。不要生成完整发言。"
            ),
            "context": actor_agent_projection(game, actor_id),
            "output_schema": {
                "wants_to_speak": "boolean",
                "responds_to_turn_id": "string|null",
                "intent": "short string",
                "urgency": "low|normal|high",
            },
        }
        return SpeechIntent.model_validate(self._request(api_key, game, payload, 240))

    def resolve_post_scene(
        self,
        *,
        api_key: str,
        game: StoredGame,
        actor_id: str,
    ) -> PostSceneResult:
        payload = {
            "task": "post_scene_settlement",
            "instruction": (
                "场景即将冻结。只从当前人物的职责、认知和亲历出发，形成一条私人记忆，"
                "并提出最多两个会后意图。意图只是申请，不能自行改变世界事实。需要会议或正式程序的行动必须标记。"
            ),
            "context": actor_agent_projection(game, actor_id),
            "output_schema": {
                "memory": "string",
                "intents": [
                    {
                        "kind": "contact_actor|draft_document|request_information|propose_action|none",
                        "summary": "string",
                        "target_id": "actor_id|null",
                        "title": "string|null",
                        "action_type": "string|null",
                        "requires_formal_decision": "boolean",
                    }
                ],
            },
        }
        return PostSceneResult.model_validate(self._request(api_key, game, payload, 700))

    def resolve_superior_reaction(
        self,
        *,
        api_key: str,
        game: StoredGame,
        document_id: str,
        cover_note: str,
    ) -> SuperiorReaction:
        document = next(
            (item for item in game.state["documents"] if item["id"] == document_id),
            None,
        )
        if document is None:
            raise LlmError("待报送文件不存在。")
        payload = {
            "task": "superior_document_reaction",
            "instruction": (
                "你即将收到下级报送材料。依据上级角色的职责、既有认知和材料本身，"
                "决定立即回复、设置后续反馈、延迟处理或暂不行动。不得假定材料之外的事实。"
            ),
            "context": actor_agent_projection(game, "superior"),
            "submission": {
                "title": document["title"],
                "summary": document["summary"],
                "content": document["content"],
                "annotations": document["annotations"],
                "source_document_ids": document["source_document_ids"],
                "cover_note": cover_note,
            },
            "output_schema": {
                "immediate_reply": "string",
                "reaction_kind": "immediate|conditional_follow_up|delayed|none",
                "condition": "string|null",
                "delay_days": "integer|null",
                "expires_after_days": "integer|null",
                "proposed_action": "string|null",
            },
        }
        return SuperiorReaction.model_validate(self._request(api_key, game, payload, 600))

    def _request(
        self,
        api_key: str,
        game: StoredGame,
        payload: Dict[str, Any],
        max_tokens: int,
    ) -> Dict[str, Any]:
        base = validate_api_base(game.api_base)
        body = {
            "model": game.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.42,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            response = httpx.post(
                "{}/chat/completions".format(base),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LlmError("人物 Agent 响应超时，任何场景状态都没有被部分提交。") from exc
        except httpx.HTTPError as exc:
            raise LlmError("无法连接 DeepSeek，人物输出尚未提交。") from exc
        if response.status_code == 401:
            raise LlmError("API Key 已失效，请重新输入。")
        if response.status_code >= 400:
            raise LlmError("DeepSeek 返回错误（HTTP {}）。".format(response.status_code))
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError("人物 Agent 没有返回可用的结构化 JSON。") from exc
        if not isinstance(data, dict):
            raise LlmError("人物 Agent 返回结构错误。")
        return data

    @staticmethod
    def _validate_beliefs(actor_id: str, result: AgentUtterance) -> None:
        if not set(result.used_belief_ids).issubset(set(actor_knowledge_ids(actor_id))):
            raise LlmError("人物 Agent 引用了其认知范围外的信息，输出已拒绝。")


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()
