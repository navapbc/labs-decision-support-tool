// Auth types

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  success: boolean;
  user_id?: string;
  error?: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  isLoading: boolean;
}

// Session list types

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
}

// Chat history types

export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: ChatHistoryMessage[];
}

// API Request/Response types

export interface QueryRequest {
  session_id: string;
  new_session: boolean;
  message: string;
  user_id: string;
  agency_id?: string;
  beneficiary_id?: string;
}

export interface Citation {
  citation_id: string;
  source_id: string;
  source_name: string;
  source_dataset: string;
  page_number: number | null;
  uri: string | null;
  headings: string[];
  citation_text: string;
}

export interface QueryResponse {
  response_text: string;
  alert_message?: string;
  citations: Citation[];
  response_id?: string;
}

export interface QueryInitResponse {
  status: string;
  message_id: string;
}

export interface FeedbackRequest {
  user_id: string;
  session_id: string;
  response_id: string;
  is_positive: boolean;
  comment?: string;
}

// Chat state types

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  responseId?: string;
}

export interface ChatSession {
  sessionId: string;
  userId: string;
  messages: ChatMessage[];
  isNewSession: boolean;
}

// SSE Event types
export interface SSEChunkEvent {
  event: "chunk";
  data: string;
}

export interface SSEAlertEvent {
  event: "alert";
  data: string;
}

export interface SSERemappedEvent {
  event: "remapped_response";
  data: string;
}

export interface SSEDoneEvent {
  event: "done";
  data: string; // JSON string of QueryResponse
}

export interface SSEErrorEvent {
  event: "error";
  data: string;
}

export type SSEEvent =
  | SSEChunkEvent
  | SSEAlertEvent
  | SSERemappedEvent
  | SSEDoneEvent
  | SSEErrorEvent;
