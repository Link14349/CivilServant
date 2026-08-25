export type GameMode = "live" | "template";

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

export interface Actor {
  id: string;
  name: string;
  title: string;
  public_position: string;
  known_note: string;
  work_style: string;
  relation: number;
}

export interface Responsibility {
  lead_actor_id: string | null;
  lead_label: string;
  participants: string[];
  procedure: string;
  record: string;
}

export interface Report {
  id: string;
  source: string;
  title: string;
  summary: string;
  detail: string;
  tone: "neutral" | "positive" | "cautious" | "warning" | "danger";
}

export interface GameOption {
  id: string;
  label: string;
  description: string;
  tradeoff: string;
  responsibility: Responsibility;
}

export interface Dossier {
  overview: string[];
  timeline: { time: string; event: string }[];
  stakes: { label: string; value: string; detail: string }[];
  established: string[];
  contested: string[];
  procedure: string;
}

export interface Turn {
  number: number;
  total: number;
  phase: string;
  title: string;
  date_label: string;
  briefing: string;
  dossier: Dossier;
  question: string;
  reports: Report[];
  actor_ids: string[];
  options: GameOption[];
  custom_placeholder: string;
  attention_remaining: number;
}

export interface Reaction {
  actor_id: string;
  text: string;
}

export interface HistoryEntry {
  turn: number;
  title: string;
  choice: string;
  directive_summary: string;
  narrative: string;
  effects: string[];
  npc_reactions: Reaction[];
  responsibility: Responsibility | null;
}

export type ConversationChannel = "private_meeting" | "written_inquiry";
export type ConversationIntent = "inquire" | "sound_out" | "private_assignment" | "conditional_exchange";

export interface Conversation {
  id: string;
  turn: number;
  actor_id: string;
  channel: ConversationChannel;
  intent: ConversationIntent;
  player_message: string;
  reply: string;
  disposition: string;
  consequence_note: string;
  commitment_summary: string | null;
  requires_formal_decision: boolean;
}

export interface PrivateRecord {
  id: string;
  turn: number;
  actor_id: string;
  kind: string;
  summary: string;
  status: string;
  visibility: string;
  requires_formal_decision: boolean;
}

export interface Outcome {
  grade: string;
  title: string;
  summary: string;
  achievements: string[];
  risks: string[];
  epilogue: string;
}

export interface Game {
  id: string;
  version: number;
  player_name: string;
  role_title: string;
  mode: GameMode;
  model: string;
  api_base: string;
  status: "active" | "completed";
  turn: Turn | null;
  metrics: Metric[];
  actors: Actor[];
  history: HistoryEntry[];
  commitments: string[];
  conversations: Conversation[];
  private_records: PrivateRecord[];
  outcome: Outcome | null;
}
