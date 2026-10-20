import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Sparkles,
  User,
  Bot,
  Copy,
  Check,
  BrainCircuit,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useToast } from "../layout/Toast";

export function ChatView({
  messages,
  onSendMessage,
  loading,
  onClearChat,
  sessionId: _sessionId,
}) {
  const [input, setInput] = useState("");
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [expandedMemoryMsgIndex, setExpandedMemoryMsgIndex] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const { showToast } = useToast();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!input.trim() || loading) return;
    onSendMessage(input.trim());
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleCopyMessage = (text, idx) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedIndex(idx);
      showToast("Response copied to clipboard", "success", 2000);
      setTimeout(() => setCopiedIndex(null), 2000);
    }
  };

  const renderFormattedContent = (content) => {
    if (!content) return null;

    // Detect fenced code blocks
    const parts = content.split(/(```[\s\S]*?```)/g);
    return parts.map((part, idx) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        const lines = part.slice(3, -3).split("\n");
        const lang = lines[0].trim() || "code";
        const code = lines.slice(1).join("\n");
        return (
          <div
            key={idx}
            className="code-block-wrapper"
            style={{
              margin: "12px 0",
              background: "#080c14",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "6px 12px",
                background: "rgba(255, 255, 255, 0.04)",
                borderBottom: "1px solid var(--border-subtle)",
                fontSize: "0.72rem",
                color: "var(--text-muted)",
                fontFamily: "var(--font-family-mono)",
                textTransform: "uppercase",
              }}
            >
              <span>{lang}</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  navigator?.clipboard?.writeText(code);
                  showToast("Code copied to clipboard", "success", 1800);
                }}
                style={{ padding: "2px 6px", fontSize: "0.72rem" }}
              >
                <Copy size={12} /> Copy
              </button>
            </div>
            <pre
              style={{
                margin: 0,
                padding: "12px",
                overflowX: "auto",
                fontFamily: "var(--font-family-mono)",
                fontSize: "0.82rem",
                lineHeight: 1.5,
                color: "#e2e8f0",
              }}
            >
              <code>{code}</code>
            </pre>
          </div>
        );
      }

      // Simple markdown bold & list processing
      return (
        <span key={idx} style={{ whiteSpace: "pre-wrap" }}>
          {part}
        </span>
      );
    });
  };

  return (
    <div
      className="view-container chat-view"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 64px)",
        maxWidth: "980px",
        margin: "0 auto",
        width: "100%",
        padding: "16px 20px 24px",
      }}
    >
      {/* Chat Header Actions */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          paddingBottom: "12px",
          borderBottom: "1px solid var(--border-subtle)",
          marginBottom: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className="badge badge-indigo">Nemotron 3.5</span>
          <span className="badge badge-emerald">Qwen3 Hybrid Retrieval</span>
        </div>
        {messages.length > 1 && onClearChat && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onClearChat}
            style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}
          >
            <Trash2 size={13} /> Clear Conversation
          </button>
        )}
      </div>

      {/* Message History List */}
      <div
        className="chat-messages-scroll"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "20px",
          paddingRight: "6px",
        }}
      >
        {messages.map((msg, idx) => {
          const isUser = msg.role === "user";
          const hasMemories = msg.memories_recalled && msg.memories_recalled.length > 0;
          const isMemoryExpanded = expandedMemoryMsgIndex === idx;

          return (
            <div
              key={idx}
              className={`chat-message ${isUser ? "user-message" : "assistant-message"}`}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: isUser ? "flex-end" : "flex-start",
                gap: "6px",
                width: "100%",
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: "12px",
                  maxWidth: isUser ? "85%" : "95%",
                  flexDirection: isUser ? "row-reverse" : "row",
                  alignItems: "flex-start",
                }}
              >
                {/* Avatar */}
                <div
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "8px",
                    background: isUser
                      ? "var(--accent-primary, #6366f1)"
                      : "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#ffffff",
                    flexShrink: 0,
                    boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
                  }}
                >
                  {isUser ? <User size={16} /> : <Bot size={17} />}
                </div>

                {/* Message Bubble */}
                <div
                  style={{
                    background: isUser ? "var(--accent-primary, #6366f1)" : "var(--bg-surface, #101626)",
                    border: isUser ? "none" : "1px solid var(--border-default)",
                    borderRadius: "14px",
                    padding: "14px 18px",
                    color: isUser ? "#ffffff" : "var(--text-primary)",
                    fontSize: "0.92rem",
                    lineHeight: 1.6,
                    boxShadow: "var(--shadow-sm)",
                    position: "relative",
                  }}
                >
                  {renderFormattedContent(msg.content)}

                  {/* Assistant Copy Button */}
                  {!isUser && (
                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "8px" }}>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleCopyMessage(msg.content, idx)}
                        style={{ padding: "4px 8px", fontSize: "0.72rem", color: "var(--text-muted)" }}
                      >
                        {copiedIndex === idx ? (
                          <>
                            <Check size={12} color="var(--color-success)" /> Copied
                          </>
                        ) : (
                          <>
                            <Copy size={12} /> Copy
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Transparent Memory Context Drawer */}
              {!isUser && hasMemories && (
                <div
                  style={{
                    marginLeft: "44px",
                    maxWidth: "90%",
                    borderRadius: "10px",
                    background: "rgba(99, 102, 241, 0.06)",
                    border: "1px solid rgba(99, 102, 241, 0.2)",
                    overflow: "hidden",
                    fontSize: "0.8rem",
                  }}
                >
                  {/* Collapsed Pill Trigger */}
                  <div
                    onClick={() => setExpandedMemoryMsgIndex(isMemoryExpanded ? null : idx)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 12px",
                      cursor: "pointer",
                      color: "#a5b4fc",
                      fontWeight: 500,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <BrainCircuit size={15} color="#818cf8" />
                      <span>
                        {msg.memories_recalled.length} Associated Memory
                        {msg.memories_recalled.length > 1 ? "ies" : ""} Influenced Response
                      </span>
                    </div>
                    {isMemoryExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>

                  {/* Expanded Memory Cards */}
                  {isMemoryExpanded && (
                    <div
                      style={{
                        padding: "10px 12px",
                        borderTop: "1px solid rgba(99, 102, 241, 0.15)",
                        display: "flex",
                        flexDirection: "column",
                        gap: "8px",
                      }}
                    >
                      {msg.memories_recalled.map((mem, mIdx) => (
                        <div
                          key={mIdx}
                          style={{
                            background: "var(--bg-surface)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "8px",
                            padding: "8px 10px",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: "4px",
                            }}
                          >
                            <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.82rem" }}>
                              #{mem.memory_key}
                            </span>
                            <div style={{ display: "flex", gap: "6px" }}>
                              <span className="badge badge-neutral" style={{ fontSize: "0.65rem" }}>
                                {mem.category}
                              </span>
                              <span
                                className={`badge ${
                                  mem.information_source === "explicit_statement" ? "badge-emerald" : "badge-indigo"
                                }`}
                                style={{ fontSize: "0.65rem" }}
                              >
                                {mem.information_source === "explicit_statement" ? "Explicit" : "Inferred"}
                              </span>
                            </div>
                          </div>
                          <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginBottom: "4px" }}>
                            {mem.content}
                          </div>
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              fontSize: "0.72rem",
                              color: "var(--text-muted)",
                            }}
                          >
                            <span>
                              Method: <strong>{mem.retrieval_method || "hybrid"}</strong> (Score:{" "}
                              {Math.round((mem.relevance_score || 1) * 100)}%)
                            </span>
                            {mem.retrieval_reason && (
                              <span style={{ fontStyle: "italic", maxWidth: "60%", textAlign: "right" }}>
                                {mem.retrieval_reason}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Loading Spinner */}
        {loading && (
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#ffffff",
              }}
            >
              <Bot size={17} />
            </div>
            <div
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border-default)",
                borderRadius: "14px",
                padding: "12px 18px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                color: "var(--text-muted)",
                fontSize: "0.85rem",
              }}
            >
              <Sparkles size={16} className="spinning" color="var(--accent-primary)" />
              <span>Synthesizing response with relevant memories...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <form
        onSubmit={handleSubmit}
        style={{
          marginTop: "16px",
          display: "flex",
          gap: "10px",
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-lg, 14px)",
          padding: "8px 12px",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question, share a skill, project, or preference... (Shift+Enter for newline)"
          rows={2}
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--text-primary)",
            fontFamily: "var(--font-family-sans)",
            fontSize: "0.9rem",
            resize: "none",
            lineHeight: 1.5,
          }}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!input.trim() || loading}
          style={{
            alignSelf: "flex-end",
            height: "40px",
            padding: "0 16px",
          }}
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
