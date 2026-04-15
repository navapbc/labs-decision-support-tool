"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SettingsIcon } from "lucide-react";
import type { ChatSettings } from "@/hooks/useSettings";

interface SettingsPanelProps {
  settings: ChatSettings;
  onSettingsChange: (settings: Partial<ChatSettings>) => void;
  onReset: () => void;
}

const AVAILABLE_MODELS = [
  { value: "gpt-4o", label: "OpenAI GPT-4o" },
  { value: "claude-3-5-sonnet-20240620", label: "Anthropic Claude 3.5 Sonnet" },
  { value: "gemini/gemini-1.5-pro", label: "Google Gemini 1.5 Pro" },
  { value: "gemini/gemini-2.5-pro-preview-06-05", label: "Google Gemini 2.5 Pro" },
];

export function SettingsPanel({
  settings,
  onSettingsChange,
  onReset,
}: SettingsPanelProps) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon">
          <SettingsIcon className="h-5 w-5" />
          <span className="sr-only">Settings</span>
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Chat Settings</SheetTitle>
          <SheetDescription>
            Configure the AI model and retrieval parameters.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-6">
          {/* Model Selection */}
          <div className="space-y-2">
            <Label htmlFor="llm">Language Model</Label>
            <Select
              value={settings.llm}
              onValueChange={(value) => onSettingsChange({ llm: value })}
            >
              <SelectTrigger id="llm">
                <SelectValue placeholder="Select a model" />
              </SelectTrigger>
              <SelectContent>
                {AVAILABLE_MODELS.map((model) => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              The AI model used to generate responses.
            </p>
          </div>

          {/* Retrieval K */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="retrieval_k">Number of Citations</Label>
              <span className="text-sm text-muted-foreground">
                {settings.retrieval_k}
              </span>
            </div>
            <Slider
              id="retrieval_k"
              value={[settings.retrieval_k]}
              onValueChange={([value]) =>
                onSettingsChange({ retrieval_k: value })
              }
              min={0}
              max={50}
              step={1}
            />
            <p className="text-xs text-muted-foreground">
              Maximum number of citations to retrieve for generating responses.
            </p>
          </div>

          {/* Retrieval K Min Score */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="retrieval_k_min_score">Minimum Score</Label>
              <span className="text-sm text-muted-foreground">
                {settings.retrieval_k_min_score.toFixed(2)}
              </span>
            </div>
            <Slider
              id="retrieval_k_min_score"
              value={[settings.retrieval_k_min_score]}
              onValueChange={([value]) =>
                onSettingsChange({ retrieval_k_min_score: value })
              }
              min={-1}
              max={1}
              step={0.05}
            />
            <p className="text-xs text-muted-foreground">
              Minimum relevance score required for citations (-1 = no minimum).
            </p>
          </div>

          {/* Reset Button */}
          <div className="pt-4 border-t">
            <Button
              variant="outline"
              onClick={onReset}
              className="w-full"
            >
              Reset to Defaults
            </Button>
          </div>

          {/* Note */}
          <p className="text-xs text-muted-foreground text-center">
            Note: Settings are saved locally and apply to new conversations.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
