"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import type { ChatMessage, QueryResponse } from "@/lib/types";
import { initStreamingQuery, streamQueryGenerator, sendFeedback, getChatHistory, getSessions } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";

const SESSION_STORAGE_KEY = "chat-session-id";

export function useChat(userId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");

  // Session management
  const sessionIdRef = useRef<string>("");
  const isNewSessionRef = useRef<boolean>(true);
  const userIdRef = useRef<string>(userId || "anonymous");
  const historyLoadedRef = useRef<boolean>(false);

  // Initialize session ID from localStorage on mount (client-side only)
  useEffect(() => {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) {
      sessionIdRef.current = stored;
      setCurrentSessionId(stored);
      isNewSessionRef.current = false;
    } else {
      const newId = uuidv4();
      sessionIdRef.current = newId;
      setCurrentSessionId(newId);
      localStorage.setItem(SESSION_STORAGE_KEY, newId);
      isNewSessionRef.current = true;
    }
    setSessionReady(true);
  }, []);

  // Update userId when it changes (e.g., after login)
  useEffect(() => {
    if (userId) {
      userIdRef.current = userId;
    }
  }, [userId]);

  // Load chat history when userId is available, session is ready, and session exists
  useEffect(() => {
    async function loadHistory() {
      if (!userId || !sessionReady || historyLoadedRef.current) {
        if (sessionReady && !userId) {
          setIsLoadingHistory(false);
        }
        return;
      }

      // Only try to load history for existing sessions
      if (isNewSessionRef.current) {
        setIsLoadingHistory(false);
        historyLoadedRef.current = true;
        return;
      }

      try {
        const history = await getChatHistory(userId, sessionIdRef.current);
        if (history && history.messages.length > 0) {
          // Convert history messages to ChatMessage format
          const loadedMessages: ChatMessage[] = history.messages.map((msg, index) => ({
            id: `history-${index}`,
            role: msg.role as "user" | "assistant",
            content: msg.content,
          }));
          setMessages(loadedMessages);
        } else {
          // Session exists but has no messages, or session not found
          // Treat as new session
          isNewSessionRef.current = true;
        }
      } catch (err) {
        console.error("Failed to load chat history:", err);
        // Session doesn't exist on server - treat as new session
        isNewSessionRef.current = true;
      } finally {
        setIsLoadingHistory(false);
        historyLoadedRef.current = true;
      }
    }

    loadHistory();
  }, [userId, sessionReady]);

  // Load list of past sessions
  const loadSessions = useCallback(async () => {
    if (!userId) return;

    setIsLoadingSessions(true);
    try {
      const response = await getSessions(userId);
      setSessions(response.sessions);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setIsLoadingSessions(false);
    }
  }, [userId]);

  // Load sessions when userId is available
  useEffect(() => {
    if (userId && sessionReady) {
      loadSessions();
    }
  }, [userId, sessionReady, loadSessions]);

  // Switch to a different session
  const switchSession = useCallback(async (sessionId: string) => {
    if (!userId || sessionId === sessionIdRef.current) return;

    setIsLoadingHistory(true);
    setError(null);
    setAlertMessage(null);

    try {
      const history = await getChatHistory(userId, sessionId);
      if (history && history.messages.length > 0) {
        const loadedMessages: ChatMessage[] = history.messages.map((msg, index) => ({
          id: `history-${index}`,
          role: msg.role as "user" | "assistant",
          content: msg.content,
        }));
        setMessages(loadedMessages);
      } else {
        setMessages([]);
      }

      // Update session state
      sessionIdRef.current = sessionId;
      setCurrentSessionId(sessionId);
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
      isNewSessionRef.current = false;
    } catch (err) {
      console.error("Failed to switch session:", err);
      setError("Failed to load conversation");
    } finally {
      setIsLoadingHistory(false);
    }
  }, [userId]);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return;

    setError(null);
    setAlertMessage(null);
    setIsLoading(true);

    // Add user message
    const userMessageId = uuidv4();
    const userMessage: ChatMessage = {
      id: userMessageId,
      role: "user",
      content: content.trim(),
    };

    // Add placeholder assistant message for streaming
    const assistantMessageId = uuidv4();
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    try {
      // Initialize streaming query
      let initResponse;
      try {
        initResponse = await initStreamingQuery({
          session_id: sessionIdRef.current,
          new_session: isNewSessionRef.current,
          message: content.trim(),
          user_id: userIdRef.current,
        });
      } catch (initErr) {
        // If session not found, retry as new session
        const errMsg = initErr instanceof Error ? initErr.message : "";
        if (errMsg.includes("not found") && !isNewSessionRef.current) {
          isNewSessionRef.current = true;
          initResponse = await initStreamingQuery({
            session_id: sessionIdRef.current,
            new_session: true,
            message: content.trim(),
            user_id: userIdRef.current,
          });
        } else {
          throw initErr;
        }
      }

      // After first message, session is no longer new
      isNewSessionRef.current = false;

      // Stream the response
      let streamedContent = "";
      let finalResponse: QueryResponse | null = null;

      for await (const event of streamQueryGenerator(
        initResponse.message_id,
        userIdRef.current,
        sessionIdRef.current
      )) {
        switch (event.type) {
          case "chunk":
            streamedContent += event.data;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? { ...m, content: streamedContent }
                  : m
              )
            );
            break;

          case "alert":
            setAlertMessage(event.data);
            break;

          case "remapped":
            // Update with final formatted response (with proper citation markers)
            streamedContent = event.data;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? { ...m, content: streamedContent }
                  : m
              )
            );
            break;

          case "done":
            finalResponse = event.data;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      content: finalResponse!.response_text,
                      citations: finalResponse!.citations,
                      isStreaming: false,
                      responseId: finalResponse!.response_id,
                    }
                  : m
              )
            );
            break;

          case "error":
            throw new Error(event.data);
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Unknown error";
      setError(errorMessage);

      // Update assistant message to show error
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? { ...m, content: `Error: ${errorMessage}`, isStreaming: false }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, [isLoading]);

  const submitFeedback = useCallback(
    async (responseId: string, isPositive: boolean, comment?: string) => {
      try {
        await sendFeedback({
          user_id: userIdRef.current,
          session_id: sessionIdRef.current,
          response_id: responseId,
          is_positive: isPositive,
          comment,
        });
      } catch (err) {
        console.error("Failed to submit feedback:", err);
      }
    },
    []
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    setAlertMessage(null);
    // Start a new session
    const newSessionId = uuidv4();
    sessionIdRef.current = newSessionId;
    setCurrentSessionId(newSessionId);
    localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
    isNewSessionRef.current = true;
    historyLoadedRef.current = true; // Mark as loaded since it's a new session
  }, []);

  return {
    messages,
    isLoading,
    isLoadingHistory,
    error,
    alertMessage,
    sendMessage,
    submitFeedback,
    clearChat,
    sessionId: currentSessionId,
    sessions,
    isLoadingSessions,
    switchSession,
    loadSessions,
  };
}
