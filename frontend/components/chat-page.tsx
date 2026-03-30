"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DocPanel } from "@/components/doc-panel";
import { useStore } from "@/lib/store";
import type { ChatMessage, PendingPanel } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = "/api";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      {!isUser && (
        <div
          className="w-6 h-6 rounded-full flex-shrink-0 mr-2.5 mt-0.5 flex items-center justify-center text-[9px] font-bold text-white"
          style={{ background: "#2563b0", fontFamily: "var(--font-jetbrains, monospace)" }}
        >
          M
        </div>
      )}
      <div
        className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? "bg-[#2563b0] text-white rounded-br-sm"
            : "bg-white text-[#1a1a2e] rounded-bl-sm shadow-sm border border-[#e5e7eb]"
        }`}
        style={{ fontFamily: "var(--font-dm-sans, 'DM Sans'), system-ui, sans-serif" }}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{msg.content}</span>
        ) : (
          <MarkdownContent content={msg.content} />
        )}
      </div>
    </div>
  );
}

function MarkdownContent({ content, cursor }: { content: string; cursor?: boolean }) {
  return (
    <div
      className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:my-2 prose-headings:font-semibold prose-pre:bg-[#f4f4f0] prose-pre:border prose-pre:border-[#d4d4c8] prose-pre:rounded-md prose-code:text-[#2563b0] prose-code:bg-[#dbeafe] prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-normal prose-strong:font-semibold prose-strong:text-[#1a1a2e] prose-p:leading-relaxed"
      style={{ fontFamily: "var(--font-dm-sans, 'DM Sans'), system-ui, sans-serif", color: "#1a1a2e" }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      {cursor && <span className="inline-block w-0.5 h-4 bg-[#2563b0] ml-0.5 animate-pulse align-text-bottom" />}
    </div>
  );
}

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-start mb-4">
      <div
        className="w-6 h-6 rounded-full flex-shrink-0 mr-2.5 mt-0.5 flex items-center justify-center text-[9px] font-bold text-white"
        style={{ background: "#2563b0", fontFamily: "var(--font-jetbrains, monospace)" }}
      >
        M
      </div>
      <div
        className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm leading-relaxed bg-white text-[#1a1a2e] shadow-sm border border-[#e5e7eb]"
        style={{ fontFamily: "var(--font-dm-sans, 'DM Sans'), system-ui, sans-serif" }}
      >
        <MarkdownContent content={content} cursor />
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex justify-start mb-4">
      <div
        className="w-6 h-6 rounded-full flex-shrink-0 mr-2.5 mt-0.5 flex items-center justify-center text-[9px] font-bold text-white"
        style={{ background: "#2563b0" }}
      >
        M
      </div>
      <div className="bg-white border border-[#e5e7eb] shadow-sm rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-[#9090b0] animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-[#9090b0] animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-[#9090b0] animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}

export function ChatPage() {
  const { messages, addMessage, user, panelDocId, applyPendingPanel } = useStore();
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, streaming]);

  async function handleSend() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    const history = [...messages];
    addMessage({ role: "user", content: text });
    setStreaming(true);
    setStreamingContent("");

    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history, user }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) throw new Error(await res.text());

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const event = JSON.parse(raw) as
              | { type: "text"; content: string }
              | { type: "done"; pending_panel: PendingPanel | null };

            if (event.type === "text") {
              accumulated += event.content;
              setStreamingContent(accumulated);
            } else if (event.type === "done") {
              addMessage({ role: "assistant", content: accumulated });
              setStreamingContent("");
              if (event.pending_panel) applyPendingPanel(event.pending_panel);
            }
          } catch {
            // skip malformed line
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        addMessage({
          role: "assistant",
          content: `Error: ${e instanceof Error ? e.message : "Error desconocido"}`,
        });
        setStreamingContent("");
      }
    } finally {
      setStreaming(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const hasPanel = !!panelDocId;
  const showThinking = streaming && streamingContent === "";
  const showStreaming = streaming && streamingContent !== "";

  return (
    <div className="flex h-full">
      {/* Chat column */}
      <div
        className={`flex flex-col h-full transition-all duration-200 ${
          hasPanel ? "w-[45%]" : "flex-1"
        }`}
      >
        {/* Messages — centradas con max-width */}
        <div className="flex-1 overflow-y-auto py-6">
          <div className="max-w-2xl mx-auto px-4">
            {messages.length === 0 && !streaming && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4">
                <div
                  className="text-3xl font-bold text-[#1a1a2e]"
                  style={{ fontFamily: "var(--font-lora, Lora), serif" }}
                >
                  memor<span style={{ color: "#2563b0" }}>IA</span>
                </div>
                <p className="text-sm text-[#9090b0] max-w-sm">
                  Podés pedirme que documente tablas, busque documentación existente o responda preguntas sobre tus datos.
                </p>
              </div>
            )}

            {messages.map((m, i) => (
              <MessageBubble key={i} msg={m} />
            ))}

            {showThinking && <ThinkingBubble />}
            {showStreaming && <StreamingBubble content={streamingContent} />}

            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input — también centrado */}
        <div className="flex-shrink-0 border-t border-[#d4d4c8] bg-[#fafaf8] py-4">
          <div className="max-w-2xl mx-auto px-4">
            <div className="flex items-end gap-2">
              <textarea
                className="flex-1 resize-none text-sm text-[#1a1a2e] bg-white border border-[#d4d4c8] rounded-2xl px-4 py-2.5 focus:outline-none focus:border-[#2563b0] min-h-[44px] max-h-36 leading-relaxed shadow-sm"
                placeholder="Escribí tu mensaje…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                style={{ fontFamily: "var(--font-dm-sans, 'DM Sans'), system-ui, sans-serif" }}
              />
              {streaming ? (
                <Button
                  size="sm"
                  className="h-11 w-11 p-0 flex-shrink-0 bg-red-500 hover:bg-red-600 text-white rounded-2xl shadow-sm"
                  onClick={() => abortRef.current?.abort()}
                  title="Detener respuesta"
                >
                  <Square size={13} fill="currentColor" />
                </Button>
              ) : (
                <Button
                  size="sm"
                  className="h-11 w-11 p-0 flex-shrink-0 bg-[#2563b0] hover:bg-[#1d4ed8] text-white rounded-2xl shadow-sm"
                  onClick={handleSend}
                  disabled={!input.trim()}
                >
                  <Send size={15} />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Panel */}
      {hasPanel && (
        <div className="flex-1 h-full">
          <DocPanel />
        </div>
      )}
    </div>
  );
}
