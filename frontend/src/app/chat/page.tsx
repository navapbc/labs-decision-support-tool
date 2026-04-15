"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useChat } from "@/hooks/useChat";
import { useSettings } from "@/hooks/useSettings";
import { sanitizeStreamingMarkdown } from "@/lib/markdown-sanitizer";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageActions,
  MessageAction,
  MessageResponse,
} from "@/components/ai-elements/message";
import { SettingsPanel } from "@/components/chat/SettingsPanel";
import { ConversationHistory } from "@/components/chat/ConversationHistory";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  SendIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
  MessageSquareIcon,
  Loader2Icon,
  AlertCircleIcon,
  LogOutIcon,
} from "lucide-react";

export default function ChatPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, userId, logout } = useAuth();

  const {
    messages,
    isLoading,
    isLoadingHistory,
    error,
    alertMessage,
    sendMessage,
    submitFeedback,
    clearChat,
    sessionId,
    sessions,
    isLoadingSessions,
    switchSession,
    loadSessions,
  } = useChat(userId);

  const { settings, setSettings, resetSettings } = useSettings();

  // All hooks must be called before any conditional returns
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2Icon className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Don't render if not authenticated (will redirect)
  if (!isAuthenticated) {
    return null;
  }

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    const message = input;
    setInput("");
    await sendMessage(message);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold">Decision Support Tool</h1>
          <ConversationHistory
            sessions={sessions}
            currentSessionId={sessionId}
            isLoading={isLoadingSessions}
            onSelectSession={switchSession}
            onRefresh={loadSessions}
          />
        </div>
        <div className="flex items-center gap-2">
          <SettingsPanel
            settings={settings}
            onSettingsChange={setSettings}
            onReset={resetSettings}
          />
          <Button variant="ghost" size="sm" onClick={clearChat}>
            New Chat
          </Button>
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOutIcon className="mr-1 h-4 w-4" />
            Logout
          </Button>
        </div>
      </header>

      {/* Alert message */}
      {alertMessage && (
        <div className="mx-4 mt-4 flex items-center gap-2 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950 dark:text-yellow-200">
          <AlertCircleIcon className="h-4 w-4 shrink-0" />
          <p>{alertMessage}</p>
        </div>
      )}

      {/* Chat area */}
      <Conversation className="flex-1">
        {isLoadingHistory ? (
          <div className="flex h-full items-center justify-center">
            <Loader2Icon className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : messages.length === 0 ? (
          <ConversationEmptyState
            icon={<MessageSquareIcon className="h-12 w-12" />}
            title="Welcome to the Decision Support Tool"
            description="Ask questions about benefits, programs, and services available in your area."
          />
        ) : (
          <ConversationContent>
            {messages.map((message) => (
              <Message key={message.id} from={message.role}>
                <MessageContent>
                  {message.role === "assistant" ? (
                    message.content ? (
                      <MessageResponse
                        mode="streaming"
                        isAnimating={message.isStreaming}
                      >
                        {sanitizeStreamingMarkdown(message.content)}
                      </MessageResponse>
                    ) : message.isStreaming ? (
                      <div className="flex items-center gap-2">
                        <Loader2Icon className="h-4 w-4 animate-spin" />
                        <span className="text-muted-foreground">Thinking...</span>
                      </div>
                    ) : null
                  ) : (
                    <div className="whitespace-pre-wrap">{message.content}</div>
                  )}

                  {/* Citations */}
                  {message.citations && message.citations.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">
                        Sources ({message.citations.length})
                      </p>
                      <div className="space-y-2">
                        {message.citations.map((citation) => (
                          <div
                            key={citation.citation_id}
                            className="rounded-md border bg-muted/50 p-3 text-xs"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="space-y-1">
                                <p className="font-medium">
                                  {citation.source_name}
                                </p>
                                {citation.headings.length > 0 && (
                                  <p className="text-muted-foreground">
                                    {citation.headings.join(" > ")}
                                  </p>
                                )}
                                <p className="text-muted-foreground line-clamp-2">
                                  {citation.citation_text}
                                </p>
                              </div>
                              {citation.uri && (
                                <a
                                  href={citation.uri}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="shrink-0 text-primary hover:underline"
                                >
                                  View
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </MessageContent>

                {/* Feedback actions for assistant messages */}
                {message.role === "assistant" &&
                  !message.isStreaming &&
                  message.responseId && (
                    <MessageActions className="mt-2">
                      <MessageAction
                        tooltip="Helpful"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          submitFeedback(message.responseId!, true)
                        }
                      >
                        <ThumbsUpIcon className="h-4 w-4" />
                      </MessageAction>
                      <MessageAction
                        tooltip="Not helpful"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          submitFeedback(message.responseId!, false)
                        }
                      >
                        <ThumbsDownIcon className="h-4 w-4" />
                      </MessageAction>
                    </MessageActions>
                  )}
              </Message>
            ))}
          </ConversationContent>
        )}
        <ConversationScrollButton />
      </Conversation>

      {/* Error display */}
      {error && (
        <div className="mx-4 mb-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          <p>Error: {error}</p>
        </div>
      )}

      {/* Input area */}
      <div className="border-t bg-background p-4">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2">
            <div className="relative flex-1">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question..."
                className="min-h-[44px] resize-none pr-12"
                rows={1}
                disabled={isLoading}
              />
              <Button
                type="submit"
                size="icon"
                variant="ghost"
                className="absolute bottom-1 right-1"
                disabled={!input.trim() || isLoading}
              >
                {isLoading ? (
                  <Loader2Icon className="h-4 w-4 animate-spin" />
                ) : (
                  <SendIcon className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Responses are generated by AI and may not always be accurate.
          </p>
        </form>
      </div>
    </div>
  );
}
