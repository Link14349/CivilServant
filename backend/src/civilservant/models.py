from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .config import DEFAULT_API_BASE, DEFAULT_MODEL


GameMode = Literal["live", "template"]
ConversationChannel = Literal["private_meeting", "written_inquiry"]
ConversationIntent = Literal["inquire", "sound_out", "private_assignment", "conditional_exchange"]


class ValidateLlmRequest(BaseModel):
    api_base: str = Field(default=DEFAULT_API_BASE, min_length=8, max_length=512)
    model: str = Field(default=DEFAULT_MODEL, min_length=2, max_length=128)


class ValidateLlmResponse(BaseModel):
    ok: bool
    model: str
    message: str


class CreateGameRequest(BaseModel):
    player_name: str = Field(default="林砚", min_length=1, max_length=20)
    mode: GameMode = "live"
    api_base: str = Field(default=DEFAULT_API_BASE, min_length=8, max_length=512)
    model: str = Field(default=DEFAULT_MODEL, min_length=2, max_length=128)
    seed: Optional[int] = Field(default=None, ge=1, le=2_147_483_647)


class SubmitActionRequest(BaseModel):
    version: int = Field(ge=1)
    option_id: Optional[str] = Field(default=None, max_length=128)
    custom_text: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_one_action(self) -> "SubmitActionRequest":
        if bool(self.option_id) == bool(self.custom_text and self.custom_text.strip()):
            raise ValueError("请选择一个预设选项，或填写其他方案")
        return self


class SubmitConversationRequest(BaseModel):
    version: int = Field(ge=1)
    actor_id: str = Field(min_length=2, max_length=128)
    channel: ConversationChannel = "private_meeting"
    intent: ConversationIntent = "inquire"
    message: str = Field(min_length=2, max_length=1200)


class MetricView(BaseModel):
    id: str
    label: str
    value: int
    description: str
    higher_is_better: bool = True


class ActorView(BaseModel):
    id: str
    name: str
    title: str
    public_position: str
    known_note: str
    work_style: str
    relation: int


class ReportView(BaseModel):
    id: str
    source: str
    title: str
    summary: str
    detail: str
    tone: str = "neutral"


class TimelineItemView(BaseModel):
    time: str
    event: str


class StakeView(BaseModel):
    label: str
    value: str
    detail: str


class DossierView(BaseModel):
    overview: List[str]
    timeline: List[TimelineItemView]
    stakes: List[StakeView]
    established: List[str]
    contested: List[str]
    procedure: str


class ResponsibilityView(BaseModel):
    lead_actor_id: Optional[str] = None
    lead_label: str
    participants: List[str]
    procedure: str
    record: str


class OptionView(BaseModel):
    id: str
    label: str
    description: str
    tradeoff: str
    responsibility: ResponsibilityView


class TurnView(BaseModel):
    number: int
    total: int = 6
    phase: str
    title: str
    date_label: str
    briefing: str
    dossier: DossierView
    question: str
    reports: List[ReportView]
    actor_ids: List[str]
    options: List[OptionView]
    custom_placeholder: str
    attention_remaining: int


class ConversationView(BaseModel):
    id: str
    turn: int
    actor_id: str
    channel: ConversationChannel
    intent: ConversationIntent
    player_message: str
    reply: str
    disposition: str
    consequence_note: str
    commitment_summary: Optional[str] = None
    requires_formal_decision: bool = False


class PrivateRecordView(BaseModel):
    id: str
    turn: int
    actor_id: str
    kind: str
    summary: str
    status: str
    visibility: str = "一对一知情"
    requires_formal_decision: bool = False


class HistoryEntryView(BaseModel):
    turn: int
    title: str
    choice: str
    directive_summary: str
    narrative: str
    effects: List[str]
    npc_reactions: List[Dict[str, str]]
    responsibility: Optional[ResponsibilityView] = None


class OutcomeView(BaseModel):
    grade: str
    title: str
    summary: str
    achievements: List[str]
    risks: List[str]
    epilogue: str


class GameView(BaseModel):
    id: str
    version: int
    player_name: str
    role_title: str = "岚州市委书记"
    mode: GameMode
    model: str
    api_base: str
    status: Literal["active", "completed"]
    turn: Optional[TurnView]
    metrics: List[MetricView]
    actors: List[ActorView]
    history: List[HistoryEntryView]
    commitments: List[str]
    conversations: List[ConversationView]
    private_records: List[PrivateRecordView]
    outcome: Optional[OutcomeView] = None


class ParsedAction(BaseModel):
    strategy_tag: str
    directive_summary: str
    narrative: str
    npc_reactions: List[Dict[str, str]] = Field(default_factory=list)


class ParsedConversation(BaseModel):
    reply: str = Field(min_length=2, max_length=1600)
    disposition: Literal[
        "inform",
        "cautious",
        "accept",
        "tentative_accept",
        "decline",
        "needs_formalization",
    ]
    used_belief_ids: List[str] = Field(default_factory=list, max_length=8)
    commitment_summary: Optional[str] = Field(default=None, max_length=300)
    requires_formal_decision: bool = False
    consequence_note: str = Field(min_length=2, max_length=300)


class StoredGame(BaseModel):
    id: str
    version: int
    player_name: str
    mode: GameMode
    model: str
    api_base: str
    seed: int
    turn_index: int
    status: Literal["active", "completed"]
    state: Dict[str, Any]
    history: List[Dict[str, Any]]
    outcome: Optional[Dict[str, Any]] = None
