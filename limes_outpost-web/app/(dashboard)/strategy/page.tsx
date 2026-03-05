// app/(dashboard)/strategy/page.tsx
"use client";

import { useState } from "react";
import { useVentureStore } from "@/store";
import { Sparkles, Send, Bot, User, ShieldCheck, Loader2, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

export default function StrategyPage() {
  const activeVentureId = useVentureStore((s) => s.activeVentureId);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || !activeVentureId || isLoading) return;

    const userMessage = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const res = await api.post(`/ventures/${activeVentureId}/strategy/chat`, {
        message: userMessage,
      });

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.content },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I'm having trouble connecting to the strategy core. Check your API keys.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-theme(spacing.32))] max-w-5xl mx-auto w-full">
      {/* Header Area */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center border border-accent/20">
            <Sparkles className="w-6 h-6 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ink-primary">
              Strategy Room
            </h1>
            <p className="text-sm text-ink-muted flex items-center gap-1.5 mt-1">
              <ShieldCheck className="w-3.5 h-3.5 text-success" />
              Connected to{" "}
              <span className="font-mono text-accent">
                {activeVentureId || "global-context"}
              </span>
            </p>
          </div>
        </div>

        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-ink-muted hover:text-error transition-colors border border-border rounded-lg hover:bg-error/5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear Chat
          </button>
        )}
      </div>

      {/* Chat History Area */}
      <div className="flex-1 overflow-y-auto border border-border rounded-xl bg-surface/50 p-6 flex flex-col gap-6">
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="max-w-md space-y-4">
              <div className="w-16 h-16 bg-elevated rounded-full flex items-center justify-center mx-auto border border-border">
                <Bot className="w-8 h-8 text-ink-secondary" />
              </div>
              <h2 className="text-lg font-semibold text-ink-primary">
                The Strategist is ready.
              </h2>
              <p className="text-sm text-ink-secondary leading-relaxed">
                I have access to your brand profile and personal preferences. Ask
                me to draft a content plan, analyze a niche, or refine your brand
                voice.
              </p>
              <div className="grid grid-cols-2 gap-2 pt-4">
                {[
                  "Review Brand Voice",
                  "Next 30 Day Plan",
                  "Identify Blockers",
                  "Content Ideas",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    className="text-xs p-2 rounded-md bg-elevated border border-border hover:border-accent/50 transition-colors text-ink-muted hover:text-ink-primary"
                    onClick={() => setInput(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-4 max-w-[80%]",
                msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
              )}
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center border shrink-0",
                  msg.role === "user"
                    ? "bg-accent/10 border-accent/20"
                    : "bg-elevated border-border"
                )}
              >
                {msg.role === "user" ? (
                  <User className="w-4 h-4 text-accent" />
                ) : (
                  <Bot className="w-4 h-4 text-ink-secondary" />
                )}
              </div>
              <div
                className={cn(
                  "p-4 rounded-2xl text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-accent text-white shadow-sm"
                    : "bg-elevated border border-border text-ink-primary"
                )}
              >
                {msg.content}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex gap-4 mr-auto">
            <div className="w-8 h-8 rounded-full flex items-center justify-center border bg-elevated border-border shrink-0">
              <Loader2 className="w-4 h-4 text-ink-muted animate-spin" />
            </div>
            <div className="p-4 rounded-2xl bg-elevated border border-border text-ink-muted text-sm italic">
              Thinking...
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="mt-6 relative">
        <textarea
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="What are we building today?"
          className="w-full bg-surface border border-border rounded-xl py-4 pl-5 pr-14 text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all resize-none shadow-sm"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          className={cn(
            "absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-lg transition-all",
            input.trim() && !isLoading
              ? "bg-accent text-white shadow-lg"
              : "text-ink-muted"
          )}
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
      <p className="text-[10px] text-center text-ink-muted mt-3 uppercase tracking-widest font-mono">
        Autonomous Strategy Engine v1.0
      </p>
    </div>
  );
}