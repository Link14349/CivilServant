from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .config import DEFAULT_API_BASE, DEFAULT_MODEL
from .models import GameMode, MetricView


SceneKind = Literal["conversation", "meeting", "superior_meeting", "field_visit"]
ScheduleKind = Literal["conversation", "meeting", "field_visit", "superior_meeting"]
MeetingType = Literal["symposium", "secretary_special", "coordination", "standing_committee"]
DiscussionMode = Literal["free", "chaired"]
DocumentStatus = Literal[
    "draft",
    "in_review",
    "ready",
    "submitted",
    "received",
    "returned",
    "approved",
    "issued",
    "archived",
]


class CommandRequest(BaseModel):
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class CreateDailyGameRequest(BaseModel):
    player_name: str = Field(default="林砚", min_length=1, max_length=20)
    background: Literal["industry", "county", "political_legal", "general"] = "general"
    mode: GameMode = "live"
    api_base: str = Field(default=DEFAULT_API_BASE, min_length=8, max_length=512)
    model: str = Field(default=DEFAULT_MODEL, min_length=2, max_length=128)
    seed: Optional[int] = Field(default=None, ge=1, le=2_147_483_647)


class ScheduleRequest(CommandRequest):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: ScheduleKind
    title: str = Field(min_length=2, max_length=120)
    participant_ids: List[str] = Field(default_factory=list, max_length=16)
    location_id: Optional[str] = Field(default=None, max_length=128)
    meeting_type: Optional[MeetingType] = None
    discussion_mode: Optional[DiscussionMode] = None
    meeting_document_ids: List[str] = Field(default_factory=list, max_length=12)
    notified: bool = True

    @model_validator(mode="after")
    def validate_meeting_fields(self) -> "ScheduleRequest":
        if self.kind == "meeting" and (not self.meeting_type or not self.discussion_mode):
            raise ValueError("安排会议时必须选择会议类型和讨论方式")
        if self.kind != "meeting" and self.meeting_document_ids:
            raise ValueError("只有会议日程可以附带会议材料")
        return self


class CalendarUpdateRequest(CommandRequest):
    operation: Literal["cancel"]
    reason: str = Field(default="玩家调整日程", max_length=240)


class StartConversationRequest(CommandRequest):
    actor_id: str = Field(min_length=2, max_length=128)
    channel: Literal["private_meeting", "office_meeting"] = "private_meeting"
    opening: Optional[str] = Field(default=None, max_length=1200)


class StartMeetingRequest(CommandRequest):
    meeting_type: MeetingType
    discussion_mode: DiscussionMode
    title: str = Field(min_length=2, max_length=120)
    agenda: str = Field(min_length=2, max_length=1200)
    participant_ids: List[str] = Field(min_length=1, max_length=16)
    meeting_document_ids: List[str] = Field(default_factory=list, max_length=12)


class AddMeetingMaterialsRequest(CommandRequest):
    record_version: int = Field(ge=0)
    document_ids: List[str] = Field(min_length=1, max_length=12)


class PlayerSpeechRequest(CommandRequest):
    record_version: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=2400)


class GenerateMeetingSpeechRequest(CommandRequest):
    record_version: int = Field(ge=0)
    actor_id: Optional[str] = Field(default=None, max_length=128)


class CloseSceneRequest(CommandRequest):
    record_version: int = Field(ge=0)
    resolution: Optional[str] = Field(default=None, max_length=1200)


class MeetingVoteRequest(CommandRequest):
    record_version: int = Field(ge=0)
    resolution: str = Field(min_length=2, max_length=1200)


class FieldVisitRequest(CommandRequest):
    location_id: Literal["beishan_park", "employment_center", "flood_site"]
    notified: bool = True


class DocumentActionRequest(CommandRequest):
    operation: Literal["annotate", "return", "forward", "archive"]
    note: str = Field(default="", max_length=1200)
    recipient_id: Optional[str] = Field(default=None, max_length=128)


class DraftDocumentRequest(CommandRequest):
    author_id: str = Field(default="secretary_general", max_length=128)
    title: str = Field(min_length=2, max_length=160)
    document_type: Literal["report", "briefing", "request", "meeting_material"] = "report"
    instructions: str = Field(min_length=2, max_length=2000)
    source_document_ids: List[str] = Field(default_factory=list, max_length=12)


class SubmitDocumentRequest(CommandRequest):
    recipient_id: str = Field(min_length=2, max_length=128)
    cover_note: str = Field(default="", max_length=1200)


class CloseDayRequest(CommandRequest):
    pass


class CreateNotebookNoteRequest(CommandRequest):
    title: str = Field(default="未命名笔记", min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)


class UpdateNotebookNoteRequest(CommandRequest):
    operation: Literal["update", "delete"] = "update"
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    content: Optional[str] = Field(default=None, min_length=1, max_length=12000)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "UpdateNotebookNoteRequest":
        if self.operation == "update" and self.title is None and self.content is None:
            raise ValueError("修改笔记时至少提供标题或正文")
        return self


class ActionBudgetView(BaseModel):
    total: int
    remaining: int
    reserved_today: int


class BriefingItemView(BaseModel):
    id: str
    category: Literal["news", "report", "request", "superior", "schedule", "reminder", "rumor"]
    headline: str
    summary: str
    source: str
    urgency: Literal["low", "normal", "high", "critical"] = "normal"
    document_id: Optional[str] = None
    calendar_entry_id: Optional[str] = None


class MeetingMaterialView(BaseModel):
    document_id: str
    document_version: int
    title: str
    document_type: str
    author_id: str
    author_label: str
    confidentiality: str
    summary: str
    content: str
    source_document_ids: List[str]
    formal_effect: str
    annotations: List[str]
    distribution_kind: Literal["pre_meeting", "during_meeting"]
    distributed_record_version: int
    audience_ids: List[str]


class CalendarEntryView(BaseModel):
    id: str
    date: str
    kind: ScheduleKind
    title: str
    participant_ids: List[str]
    participant_labels: List[str]
    location_id: Optional[str] = None
    location_label: Optional[str] = None
    meeting_type: Optional[MeetingType] = None
    discussion_mode: Optional[DiscussionMode] = None
    meeting_materials: List[MeetingMaterialView] = Field(default_factory=list)
    action_cost: int
    mandatory: bool
    status: Literal["scheduled", "tentative", "due", "active", "completed", "canceled", "conflict"]
    source: str
    notified: bool = True


class DocumentView(BaseModel):
    id: str
    version: int
    title: str
    document_type: str
    author_id: str
    author_label: str
    status: DocumentStatus
    confidentiality: str
    created_date: str
    due_date: Optional[str] = None
    summary: str
    content: str
    recipient_ids: List[str]
    source_document_ids: List[str]
    formal_effect: str
    annotations: List[str]


class DailyActorView(BaseModel):
    id: str
    name: str
    title: str
    public_position: str
    known_note: str
    work_style: str
    relation: int
    availability: str
    directory_group: str


class ReferenceSectionView(BaseModel):
    heading: str
    body: str


class ReferenceMaterialView(BaseModel):
    id: str
    category: str
    title: str
    subtitle: str
    updated_date: str
    summary: str
    sections: List[ReferenceSectionView]
    source_note: str


class IssueView(BaseModel):
    id: str
    title: str
    summary: str
    pressure: Literal["low", "medium", "high", "critical"]
    deadline: Optional[str] = None
    known_status: str


class SceneParticipantView(BaseModel):
    actor_id: str
    name: str
    title: str
    attendance_role: Literal["chair", "member", "invitee", "counterpart"]
    can_vote: bool = False


class TranscriptTurnView(BaseModel):
    id: str
    speaker_id: str
    speaker_name: str
    speaker_type: Literal["player", "npc", "system"]
    text: str
    record_version: int


class GenerationView(BaseModel):
    id: str
    status: Literal["idle", "thinking", "completed", "canceled", "discarded", "failed"]
    actor_id: Optional[str] = None
    message: str = ""


class ActiveSceneView(BaseModel):
    id: str
    kind: SceneKind
    title: str
    status: Literal["active", "settling"]
    action_cost: int
    record_version: int
    meeting_type: Optional[MeetingType] = None
    discussion_mode: Optional[DiscussionMode] = None
    agenda: Optional[str] = None
    location_id: Optional[str] = None
    notified: Optional[bool] = None
    participants: List[SceneParticipantView]
    meeting_materials: List[MeetingMaterialView] = Field(default_factory=list)
    transcript: List[TranscriptTurnView]
    generation: GenerationView
    silence_count: int = 0
    can_vote: bool = False
    vote_result: Optional[str] = None


class NotificationView(BaseModel):
    id: str
    date: str
    title: str
    detail: str
    tone: Literal["neutral", "positive", "warning", "danger"] = "neutral"


class ActivityView(BaseModel):
    id: str
    date: str
    kind: str
    title: str
    summary: str
    visible: bool = True


class NotebookNoteView(BaseModel):
    id: str
    title: str
    content: str
    created_date: str
    updated_date: str


class ActionCatalogItemView(BaseModel):
    id: str
    label: str
    description: str
    action_cost: int


class ActionCatalogView(BaseModel):
    meeting_types: List[ActionCatalogItemView]
    locations: List[ActionCatalogItemView]


class DailyGameView(BaseModel):
    id: str
    version: int
    schema_version: int
    player_name: str
    role_title: str = "岚州市委书记"
    background: str
    mode: GameMode
    model: str
    api_base: str
    status: Literal["active", "completed"]
    current_date: str
    day_number: int
    day_phase: Literal["reviewing", "action", "scene_active", "settling"]
    action_budget: ActionBudgetView
    briefing: List[BriefingItemView]
    calendar: List[CalendarEntryView]
    documents: List[DocumentView]
    actors: List[DailyActorView]
    reference_materials: List[ReferenceMaterialView]
    issues: List[IssueView]
    active_scene: Optional[ActiveSceneView] = None
    metrics: List[MetricView]
    notifications: List[NotificationView]
    activity: List[ActivityView]
    notebook_notes: List[NotebookNoteView]
    pending_tasks: List[str]
    action_catalog: ActionCatalogView


class SpeechIntent(BaseModel):
    wants_to_speak: bool
    responds_to_turn_id: Optional[str] = None
    intent: str = Field(default="", max_length=200)
    urgency: Literal["low", "normal", "high"] = "normal"


class AgentToolCall(BaseModel):
    call_id: str = Field(min_length=1, max_length=80)
    name: Literal[
        "list_contacts",
        "list_visible_files",
        "read_file",
        "write_file",
        "revise_file",
        "list_memories",
        "list_scene_records",
        "read_scene_record",
        "list_todos",
        "record_knowledge",
        "record_memory",
        "record_todo",
        "record_relationship_impression",
        "record_commitment",
        "contact_actor",
        "request_information",
        "propose_action",
    ]
    arguments: Dict[str, Any] = Field(default_factory=dict)


class AgentToolEffect(BaseModel):
    kind: Literal[
        "create_document",
        "revise_document",
        "record_knowledge",
        "record_memory",
        "record_todo",
        "record_relationship_impression",
        "record_commitment",
        "contact_actor",
        "request_information",
        "propose_action",
    ]
    payload: Dict[str, Any]


class AgentUtterance(BaseModel):
    text: str = Field(min_length=1, max_length=2400)
    used_belief_ids: List[str] = Field(default_factory=list, max_length=12)
    tool_effects: List[AgentToolEffect] = Field(default_factory=list, max_length=8)


class PostSceneIntent(BaseModel):
    kind: Literal["contact_actor", "draft_document", "request_information", "propose_action", "none"]
    summary: str = Field(min_length=1, max_length=400)
    target_id: Optional[str] = Field(default=None, max_length=128)
    title: Optional[str] = Field(default=None, max_length=160)
    action_type: Optional[str] = Field(default=None, max_length=128)
    requires_formal_decision: bool = False


class PostSceneResult(BaseModel):
    memory: str = Field(min_length=1, max_length=600)
    intents: List[PostSceneIntent] = Field(default_factory=list, max_length=2)
    relationship_signal: Literal["improved", "unchanged", "strained"] = "unchanged"
    tool_effects: List[AgentToolEffect] = Field(default_factory=list, max_length=8)


class SuperiorReaction(BaseModel):
    immediate_reply: str = Field(min_length=1, max_length=800)
    reaction_kind: Literal["immediate", "conditional_follow_up", "delayed", "none"]
    condition: Optional[str] = Field(default=None, max_length=200)
    delay_days: Optional[int] = Field(default=None, ge=1, le=30)
    expires_after_days: Optional[int] = Field(default=None, ge=1, le=90)
    proposed_action: Optional[str] = Field(default=None, max_length=160)
