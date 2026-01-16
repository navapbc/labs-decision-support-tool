"use client";

import { useState } from "react";
import type { SessionSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  HistoryIcon,
  MessageSquareIcon,
  Loader2Icon,
  RefreshCwIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ConversationHistoryProps {
  sessions: SessionSummary[];
  currentSessionId: string;
  isLoading: boolean;
  onSelectSession: (sessionId: string) => void;
  onRefresh: () => void;
}

function formatDate(dateString: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return "Today";
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    return date.toLocaleDateString();
  }
}

export function ConversationHistory({
  sessions,
  currentSessionId,
  isLoading,
  onSelectSession,
  onRefresh,
}: ConversationHistoryProps) {
  const [open, setOpen] = useState(false);

  const handleSelectSession = (sessionId: string) => {
    onSelectSession(sessionId);
    setOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm">
          <HistoryIcon className="mr-1 h-4 w-4" />
          History
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-80">
        <SheetHeader className="pb-2">
          <div className="flex items-center justify-between">
            <SheetTitle>Conversation History</SheetTitle>
            <Button
              variant="ghost"
              size="icon"
              onClick={onRefresh}
              disabled={isLoading}
            >
              <RefreshCwIcon
                className={cn("h-4 w-4", isLoading && "animate-spin")}
              />
            </Button>
          </div>
        </SheetHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2Icon className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <MessageSquareIcon className="mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No previous conversations
            </p>
          </div>
        ) : (
          <ScrollArea className="h-[calc(100vh-100px)]">
            <div className="space-y-1 pr-4">
              {sessions.map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => handleSelectSession(session.session_id)}
                  className={cn(
                    "w-full rounded-lg px-3 py-3 text-left transition-colors hover:bg-accent",
                    session.session_id === currentSessionId && "bg-accent"
                  )}
                >
                  <p className="line-clamp-2 text-sm font-medium">
                    {session.title}
                  </p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatDate(session.created_at)}</span>
                    <span>·</span>
                    <span>{session.message_count} messages</span>
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}
