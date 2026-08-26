import type {
  AppConfig,
  Credentials,
  DiscussionMode,
  Game,
  GameMode,
  MeetingType,
  ScheduleKind,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the safe generic message.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

function headers(game: Game, credentials: Credentials): Record<string, string> {
  const value: Record<string, string> = { "Content-Type": "application/json" };
  if (game.mode === "live") value["X-DeepSeek-API-Key"] = credentials.apiKey;
  return value;
}

function command(game: Game): { version: number; idempotency_key: string } {
  return { version: game.version, idempotency_key: crypto.randomUUID() };
}

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/config");
}

export function validateCredentials(credentials: Credentials): Promise<{ message: string }> {
  return request<{ message: string }>("/api/llm/validate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-DeepSeek-API-Key": credentials.apiKey,
    },
    body: JSON.stringify({
      api_base: credentials.apiBase,
      model: credentials.model,
    }),
  });
}

export function createGame(
  playerName: string,
  background: string,
  mode: GameMode,
  model: string,
  apiBase: string,
): Promise<Game> {
  return request<Game>("/api/games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      player_name: playerName,
      background,
      mode,
      model,
      api_base: apiBase,
    }),
  });
}

export function loadGame(gameId: string): Promise<Game> {
  return request<Game>(`/api/games/${gameId}`);
}

export function startConversation(
  game: Game,
  credentials: Credentials,
  actorId: string,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/conversations`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      actor_id: actorId,
      channel: "private_meeting",
    }),
  });
}

export function startMeeting(
  game: Game,
  credentials: Credentials,
  value: {
    meeting_type: MeetingType;
    discussion_mode: DiscussionMode;
    title: string;
    agenda: string;
    participant_ids: string[];
    meeting_document_ids: string[];
  },
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/meetings`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), ...value }),
  });
}

export function addMeetingMaterials(
  game: Game,
  credentials: Credentials,
  documentIds: string[],
): Promise<Game> {
  if (!game.active_scene || game.active_scene.kind !== "meeting") {
    throw new Error("当前没有会议场景。");
  }
  return request<Game>(
    `/api/games/${game.id}/scenes/${game.active_scene.id}/materials`,
    {
      method: "POST",
      headers: headers(game, credentials),
      body: JSON.stringify({
        ...command(game),
        record_version: game.active_scene.record_version,
        document_ids: documentIds,
      }),
    },
  );
}

export function startFieldVisit(
  game: Game,
  credentials: Credentials,
  locationId: string,
  notified: boolean,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/field-visits`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      location_id: locationId,
      notified,
    }),
  });
}

export function sendPlayerSpeech(
  game: Game,
  credentials: Credentials,
  text: string,
): Promise<Game> {
  if (!game.active_scene) throw new Error("当前没有互动场景。");
  return request<Game>(
    `/api/games/${game.id}/scenes/${game.active_scene.id}/player-speeches`,
    {
      method: "POST",
      headers: headers(game, credentials),
      body: JSON.stringify({
        ...command(game),
        record_version: game.active_scene.record_version,
        text,
      }),
    },
  );
}

export function generateMeetingSpeech(
  game: Game,
  credentials: Credentials,
  actorId?: string,
): Promise<Game> {
  if (!game.active_scene) throw new Error("当前没有会议场景。");
  return request<Game>(
    `/api/games/${game.id}/scenes/${game.active_scene.id}/meeting-speech`,
    {
      method: "POST",
      headers: headers(game, credentials),
      body: JSON.stringify({
        ...command(game),
        record_version: game.active_scene.record_version,
        actor_id: actorId,
      }),
    },
  );
}

export function voteMeeting(
  game: Game,
  credentials: Credentials,
  resolution: string,
): Promise<Game> {
  if (!game.active_scene) throw new Error("当前没有会议场景。");
  return request<Game>(`/api/games/${game.id}/scenes/${game.active_scene.id}/vote`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      record_version: game.active_scene.record_version,
      resolution,
    }),
  });
}

export function finishScene(
  game: Game,
  credentials: Credentials,
  resolution = "",
): Promise<Game> {
  if (!game.active_scene) throw new Error("当前没有互动场景。");
  return request<Game>(`/api/games/${game.id}/scenes/${game.active_scene.id}/close`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      record_version: game.active_scene.record_version,
      resolution: resolution || null,
    }),
  });
}

export function scheduleEntry(
  game: Game,
  credentials: Credentials,
  value: {
    date: string;
    kind: ScheduleKind;
    title: string;
    participant_ids: string[];
    location_id?: string;
    meeting_type?: MeetingType;
    discussion_mode?: DiscussionMode;
    meeting_document_ids?: string[];
    notified: boolean;
  },
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/calendar-entries`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), ...value }),
  });
}

export function cancelEntry(
  game: Game,
  credentials: Credentials,
  entryId: string,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/calendar-entries/${entryId}`, {
    method: "PATCH",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), operation: "cancel", reason: "玩家调整日程" }),
  });
}

export function createNotebookNote(
  game: Game,
  credentials: Credentials,
  title: string,
  content: string,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/notebook-notes`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), title, content }),
  });
}

export function updateNotebookNote(
  game: Game,
  credentials: Credentials,
  noteId: string,
  value: { operation: "update" | "delete"; title?: string; content?: string },
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/notebook-notes/${noteId}`, {
    method: "PATCH",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), ...value }),
  });
}

export function actOnDocument(
  game: Game,
  credentials: Credentials,
  documentId: string,
  operation: "annotate" | "return" | "forward" | "archive",
  note: string,
  recipientId?: string,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/documents/${documentId}/actions`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      operation,
      note,
      recipient_id: recipientId,
    }),
  });
}

export function requestDraft(
  game: Game,
  credentials: Credentials,
  value: {
    author_id: string;
    title: string;
    document_type: "report" | "briefing" | "request" | "meeting_material";
    instructions: string;
    source_document_ids: string[];
  },
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/document-tasks`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({ ...command(game), ...value }),
  });
}

export function submitDocument(
  game: Game,
  credentials: Credentials,
  documentId: string,
  recipientId: string,
  coverNote: string,
): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/documents/${documentId}/submit`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify({
      ...command(game),
      recipient_id: recipientId,
      cover_note: coverNote,
    }),
  });
}

export function finishDay(game: Game, credentials: Credentials): Promise<Game> {
  return request<Game>(`/api/games/${game.id}/days/current/close`, {
    method: "POST",
    headers: headers(game, credentials),
    body: JSON.stringify(command(game)),
  });
}
