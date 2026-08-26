export type GameMode = "live" | "template";
export type SceneKind = "conversation" | "meeting" | "superior_meeting" | "field_visit";
export type ScheduleKind = SceneKind;
export type MeetingType = "symposium" | "secretary_special" | "coordination" | "standing_committee";
export type DiscussionMode = "free" | "chaired";

export interface AppConfig {
  default_model: string;
  default_api_base: string;
}

export interface Credentials {
  mode: GameMode;
  apiKey: string;
  apiBase: string;
  model: string;
  remember: boolean;
}

export interface Metric {
  id: string;
  label: string;
  value: number;
  description: string;
  higher_is_better: boolean;
}

export interface ActionBudget {
  total: number;
  remaining: number;
  reserved_today: number;
}

export interface BriefingItem {
  id: string;
  category: "news" | "report" | "request" | "superior" | "schedule" | "reminder" | "rumor";
  headline: string;
  summary: string;
  source: string;
  urgency: "low" | "normal" | "high" | "critical";
  document_id: string | null;
  calendar_entry_id: string | null;
}

export interface CalendarEntry {
  id: string;
  date: string;
  kind: ScheduleKind;
  title: string;
  participant_ids: string[];
  participant_labels: string[];
  location_id: string | null;
  location_label: string | null;
  meeting_type: MeetingType | null;
  discussion_mode: DiscussionMode | null;
  action_cost: number;
  mandatory: boolean;
  status: "scheduled" | "tentative" | "due" | "active" | "completed" | "canceled" | "conflict";
  source: string;
  notified: boolean;
}

export interface DocumentItem {
  id: string;
  version: number;
  title: string;
  document_type: string;
  author_id: string;
  author_label: string;
  status: "draft" | "in_review" | "ready" | "submitted" | "received" | "returned" | "approved" | "issued" | "archived";
  confidentiality: string;
  created_date: string;
  due_date: string | null;
  summary: string;
  content: string;
  recipient_ids: string[];
  source_document_ids: string[];
  formal_effect: string;
  annotations: string[];
}

export interface Actor {
  id: string;
  name: string;
  title: string;
  public_position: string;
  known_note: string;
  work_style: string;
  relation: number;
  availability: string;
  directory_group: string;
}

export interface ReferenceSection {
  heading: string;
  body: string;
}

export interface ReferenceMaterial {
  id: string;
  category: string;
  title: string;
  subtitle: string;
  updated_date: string;
  summary: string;
  sections: ReferenceSection[];
  source_note: string;
}

export interface Issue {
  id: string;
  title: string;
  summary: string;
  pressure: "low" | "medium" | "high" | "critical";
  deadline: string | null;
  known_status: string;
}

export interface SceneParticipant {
  actor_id: string;
  name: string;
  title: string;
  attendance_role: "chair" | "member" | "invitee" | "counterpart";
  can_vote: boolean;
}

export interface TranscriptTurn {
  id: string;
  speaker_id: string;
  speaker_name: string;
  speaker_type: "player" | "npc" | "system";
  text: string;
  record_version: number;
}

export interface Generation {
  id: string;
  status: "idle" | "thinking" | "completed" | "canceled" | "discarded" | "failed";
  actor_id: string | null;
  message: string;
}

export interface ActiveScene {
  id: string;
  kind: SceneKind;
  title: string;
  status: "active" | "settling";
  action_cost: number;
  record_version: number;
  meeting_type: MeetingType | null;
  discussion_mode: DiscussionMode | null;
  agenda: string | null;
  location_id: string | null;
  notified: boolean | null;
  participants: SceneParticipant[];
  transcript: TranscriptTurn[];
  generation: Generation;
  silence_count: number;
  can_vote: boolean;
  vote_result: string | null;
}

export interface Notification {
  id: string;
  date: string;
  title: string;
  detail: string;
  tone: "neutral" | "positive" | "warning" | "danger";
}

export interface Activity {
  id: string;
  date: string;
  kind: string;
  title: string;
  summary: string;
  visible: boolean;
}

export interface ActionCatalogItem {
  id: string;
  label: string;
  description: string;
  action_cost: number;
}

export interface ActionCatalog {
  meeting_types: ActionCatalogItem[];
  locations: ActionCatalogItem[];
}

export interface Game {
  id: string;
  version: number;
  schema_version: number;
  player_name: string;
  role_title: string;
  background: string;
  mode: GameMode;
  model: string;
  api_base: string;
  status: "active" | "completed";
  current_date: string;
  day_number: number;
  day_phase: "reviewing" | "action" | "scene_active" | "settling";
  action_budget: ActionBudget;
  briefing: BriefingItem[];
  calendar: CalendarEntry[];
  documents: DocumentItem[];
  actors: Actor[];
  reference_materials: ReferenceMaterial[];
  issues: Issue[];
  active_scene: ActiveScene | null;
  metrics: Metric[];
  notifications: Notification[];
  activity: Activity[];
  pending_tasks: string[];
  action_catalog: ActionCatalog;
}
