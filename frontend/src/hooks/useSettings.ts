"use client";

import { useState, useEffect, useCallback } from "react";

export interface ChatSettings {
  llm: string;
  retrieval_k: number;
  retrieval_k_min_score: number;
}

const DEFAULT_SETTINGS: ChatSettings = {
  llm: "gpt-4o",
  retrieval_k: 25,
  retrieval_k_min_score: -1,
};

const STORAGE_KEY = "chat-settings";

export function useSettings() {
  const [settings, setSettingsState] = useState<ChatSettings>(DEFAULT_SETTINGS);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load settings from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        setSettingsState({ ...DEFAULT_SETTINGS, ...parsed });
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
    setIsLoaded(true);
  }, []);

  // Save settings to localStorage
  const setSettings = useCallback((newSettings: Partial<ChatSettings>) => {
    setSettingsState((prev) => {
      const updated = { ...prev, ...newSettings };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to save settings:", err);
      }
      return updated;
    });
  }, []);

  const resetSettings = useCallback(() => {
    setSettingsState(DEFAULT_SETTINGS);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error("Failed to reset settings:", err);
    }
  }, []);

  return {
    settings,
    setSettings,
    resetSettings,
    isLoaded,
  };
}
