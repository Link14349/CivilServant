import type {
  AppConfig,
  ConversationChannel,
  ConversationIntent,
  Credentials,
  Game,
  GameMode,
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
  mode: GameMode,
  model: string,
  apiBase: string,
): Promise<Game> {
  return request<Game>("/api/games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      player_name: playerName,
      mode,
      model,
      api_base: apiBase,
    }),
  });
}

export function loadGame(gameId: string): Promise<Game> {
  return request<Game>(`/api/games/${gameId}`);
}

export function submitAction(
  game: Game,
  credentials: Credentials,
  action: { option_id?: string; custom_text?: string },
): Promise<Game> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (game.mode === "live") headers["X-DeepSeek-API-Key"] = credentials.apiKey;
  return request<Game>(`/api/games/${game.id}/actions`, {
    method: "POST",
    headers,
    body: JSON.stringify({ version: game.version, ...action }),
  });
}

export function submitConversation(
  game: Game,
  credentials: Credentials,
  conversation: {
    actor_id: string;
    channel: ConversationChannel;
    intent: ConversationIntent;
    message: string;
  },
): Promise<Game> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (game.mode === "live") headers["X-DeepSeek-API-Key"] = credentials.apiKey;
  return request<Game>(`/api/games/${game.id}/conversations`, {
    method: "POST",
    headers,
    body: JSON.stringify({ version: game.version, ...conversation }),
  });
}
