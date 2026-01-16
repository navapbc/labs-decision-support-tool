import type {
  QueryRequest,
  QueryResponse,
  QueryInitResponse,
  FeedbackRequest,
  LoginRequest,
  LoginResponse,
  ChatHistoryResponse,
  SessionListResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Auth API

export async function login(params: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function sendQuery(params: QueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function initStreamingQuery(
  params: QueryRequest
): Promise<QueryInitResponse> {
  const response = await fetch(`${API_BASE}/api/query_init`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export interface StreamCallbacks {
  onChunk: (chunk: string) => void;
  onAlert?: (alert: string) => void;
  onRemapped?: (content: string) => void;
  onDone: (response: QueryResponse) => void;
  onError: (error: string) => void;
}

export async function streamQuery(
  messageId: string,
  userId: string,
  sessionId: string,
  callbacks: StreamCallbacks
): Promise<void> {
  const params = new URLSearchParams({
    id: messageId,
    user_id: userId,
    session_id: sessionId,
  });

  const response = await fetch(`${API_BASE}/api/query_stream?${params}`);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          const eventType = line.slice(7).trim();
          continue;
        }
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          // Parse based on most recent event type
          // For simplicity, we handle common patterns
          if (data === "[DONE]") {
            continue;
          }
          // The SSE format sends event: then data: on next line
          // We need to track the event type
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// More robust SSE parser
export async function* streamQueryGenerator(
  messageId: string,
  userId: string,
  sessionId: string
): AsyncGenerator<
  | { type: "chunk"; data: string }
  | { type: "alert"; data: string }
  | { type: "remapped"; data: string }
  | { type: "done"; data: QueryResponse }
  | { type: "error"; data: string }
> {
  const params = new URLSearchParams({
    id: messageId,
    user_id: userId,
    session_id: sessionId,
  });

  const response = await fetch(`${API_BASE}/api/query_stream?${params}`);

  if (!response.ok) {
    yield { type: "error", data: `HTTP ${response.status}` };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", data: "No response body" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEventType = "chunk";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process line by line
      const lines = buffer.split("\n");
      // Keep the last incomplete line in the buffer
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6);

          switch (currentEventType) {
            case "chunk":
              yield { type: "chunk", data };
              break;
            case "alert":
              yield { type: "alert", data };
              break;
            case "remapped_response":
              yield { type: "remapped", data };
              break;
            case "done":
              try {
                const parsed = JSON.parse(data) as QueryResponse;
                yield { type: "done", data: parsed };
              } catch {
                yield { type: "error", data: "Failed to parse response" };
              }
              break;
            case "error":
              yield { type: "error", data };
              break;
          }
        }
        // Empty lines are ignored (they separate events in SSE)
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function sendFeedback(params: FeedbackRequest): Promise<void> {
  const response = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
}

export async function getEngines(
  userId: string,
  sessionId?: string
): Promise<string[]> {
  const params = new URLSearchParams({ user_id: userId });
  if (sessionId) {
    params.append("session_id", sessionId);
  }

  const response = await fetch(`${API_BASE}/api/engines?${params}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function healthcheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/healthcheck`);
    return response.ok;
  } catch {
    return false;
  }
}

export async function getSessions(
  userId: string
): Promise<SessionListResponse> {
  const params = new URLSearchParams({ user_id: userId });

  const response = await fetch(`${API_BASE}/api/sessions?${params}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function getChatHistory(
  userId: string,
  sessionId: string
): Promise<ChatHistoryResponse | null> {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });

  try {
    const response = await fetch(`${API_BASE}/api/chat_history?${params}`);

    if (response.status === 404) {
      // Session not found - this is expected for new sessions
      return null;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  } catch (err) {
    console.error("Failed to load chat history:", err);
    return null;
  }
}
