import { useState, useEffect, useCallback } from "react";
import { BrainCircuit, Send, Sparkles, User, Trash2, Database, RefreshCw, X, Tag } from "lucide-react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function getOrCreateSessionId() {
  let id = localStorage.getItem("memora_session_id");
  if (!id) {
    id = "session_" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("memora_session_id", id);
  }
  return id;
}

function App() {
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm MEMORA AI, connected to NVIDIA Nemotron and Neon Lakebase Postgres. Share your preferences, skills, or projects, and I will remember and adapt to them across sessions."
    }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [memories, setMemories] = useState([]);
  const [loadingMemories, setLoadingMemories] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [showMemoryPanel, setShowMemoryPanel] = useState(true);

  const fetchMemories = useCallback(async () => {
    if (!sessionId) return;
    setLoadingMemories(true);
    try {
      const res = await fetch(`${API_URL}/api/memories?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const data = await res.json();
        setMemories(data.memories || []);
      }
    } catch (err) {
      console.error("Failed to fetch memories:", err);
    } finally {
      setLoadingMemories(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  async function handleSend() {
    const message = input.trim();
    if (!message || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Unable to generate a response.");
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          model: data.model,
          recalled: data.memories_recalled,
          extracted: data.memories_extracted
        }
      ]);

      // Automatically refresh memories to reflect new extractions
      fetchMemories();
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${error.message}` }
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteMemory(memoryId) {
    try {
      const res = await fetch(
        `${API_URL}/api/memories/${memoryId}?session_id=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        setMemories((prev) => prev.filter((m) => m.id !== memoryId));
      }
    } catch (err) {
      console.error("Failed to delete memory:", err);
    }
  }

  async function handleClearAllMemories() {
    if (!window.confirm("Are you sure you want to clear all active memories for this session?")) return;
    try {
      const res = await fetch(
        `${API_URL}/api/memories?session_id=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        setMemories([]);
      }
    } catch (err) {
      console.error("Failed to clear memories:", err);
    }
  }

  function handleResetSession() {
    const newId = "session_" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("memora_session_id", newId);
    setSessionId(newId);
    setMessages([
      {
        role: "assistant",
        content: `Switched to a fresh isolated session (${newId}). No memories from previous sessions will be accessed.`
      }
    ]);
  }

  const filteredMemories = memories.filter((m) => {
    if (selectedCategory === "all") return true;
    return m.category.toLowerCase() === selectedCategory.toLowerCase();
  });

  const categories = ["all", ...new Set(memories.map((m) => m.category.toLowerCase()))];

  return (
    <div className="app-shell">
      <header className="navbar">
        <div className="brand">
          <div className="brand-icon">
            <BrainCircuit size={23} />
          </div>
          <div>
            <h2>MEMORA<span> AI</span></h2>
            <p>Persistent Memory Evolution Workspace</p>
          </div>
        </div>

        <div className="nav-actions">
          <button
            className={`panel-toggle-btn ${showMemoryPanel ? "active" : ""}`}
            onClick={() => setShowMemoryPanel(!showMemoryPanel)}
            title="Toggle Memory Panel"
          >
            <Database size={16} />
            <span>Memories ({memories.length})</span>
          </button>

          <div className="connection">
            <span className="status-dot"></span>
            <span>Neon + Nemotron</span>
          </div>
        </div>
      </header>

      <main className="workspace">
        <section className="welcome">
          <div className="sparkle">
            <Sparkles size={22} />
          </div>
          <p className="eyebrow">PERSISTENT MEMORY EVOLUTION ENGINE</p>
          <h1>
            Intelligence that
            <br />
            <span>remembers & evolves.</span>
          </h1>
          <p className="subtitle">
            Powered by NVIDIA Nemotron and Neon Lakebase Postgres.
          </p>

          <div className="session-bar">
            <span className="session-tag">
              Session: <code>{sessionId}</code>
            </span>
            <button className="new-session-btn" onClick={handleResetSession} title="Start new isolated session">
              <RefreshCw size={12} /> New Session
            </button>
          </div>
        </section>

        <div className={`workspace-grid ${showMemoryPanel ? "with-sidebar" : "full-chat"}`}>
          {/* Chat Interface */}
          <section className="chat-panel">
            <div className="chat-heading">
              <div>
                <h3>AI Conversation</h3>
                <p>Chat with persistent context awareness</p>
              </div>
              <span className="model-label">NEMOTRON 3.5</span>
            </div>

            <div className="messages">
              {messages.map((msg, index) => (
                <div className={`message ${msg.role}`} key={index}>
                  <div className="avatar">
                    {msg.role === "assistant" ? <BrainCircuit size={18} /> : <User size={18} />}
                  </div>

                  <div className="message-content">
                    <span className="sender">{msg.role === "assistant" ? "MEMORA AI" : "YOU"}</span>
                    <p>{msg.content}</p>

                    {msg.recalled && msg.recalled.length > 0 && (
                      <div className="memory-chips">
                        <small className="chips-title">Recalled Context:</small>
                        {msg.recalled.map((rec, i) => (
                          <span key={i} className="chip recalled" title={rec.content}>
                            💡 {rec.memory_key}
                          </span>
                        ))}
                      </div>
                    )}

                    {msg.extracted && msg.extracted.length > 0 && (
                      <div className="memory-chips">
                        <small className="chips-title">Learned & Saved:</small>
                        {msg.extracted.map((ext, i) => (
                          <span key={i} className="chip extracted" title={ext.content}>
                            ✨ {ext.memory_key} ({Math.round(ext.confidence_score * 100)}%)
                          </span>
                        ))}
                      </div>
                    )}

                    {msg.model && <small className="model-tag">Powered by {msg.model}</small>}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="typing">
                  <span></span>
                  <span></span>
                  <span></span>
                  MEMORA is reasoning & recalling memories...
                </div>
              )}
            </div>

            <div className="input-area">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Share facts, preferences, or questions..."
                disabled={loading}
              />
              <button onClick={handleSend} disabled={loading || !input.trim()} aria-label="Send message">
                <Send size={18} />
              </button>
            </div>

            <p className="disclaimer">
              Memory Evolution Engine v1 · Scoped to session {sessionId} · Neon Postgres
            </p>
          </section>

          {/* Memory Evolution Panel */}
          {showMemoryPanel && (
            <aside className="memory-panel">
              <div className="memory-header">
                <div>
                  <h3>Memory Storage</h3>
                  <p>{memories.length} persistent fact{memories.length === 1 ? "" : "s"}</p>
                </div>
                <div className="memory-actions">
                  <button onClick={fetchMemories} className="icon-btn" title="Refresh memories" disabled={loadingMemories}>
                    <RefreshCw size={14} className={loadingMemories ? "spin" : ""} />
                  </button>
                  {memories.length > 0 && (
                    <button onClick={handleClearAllMemories} className="icon-btn danger" title="Clear all memories">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>

              {categories.length > 1 && (
                <div className="category-filters">
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      className={`filter-btn ${selectedCategory === cat ? "active" : ""}`}
                      onClick={() => setSelectedCategory(cat)}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              )}

              <div className="memory-list">
                {filteredMemories.length === 0 ? (
                  <div className="empty-memories">
                    <Database size={28} />
                    <p>No active memories in this category yet.</p>
                    <small>Tell MEMORA what you like, your skills, or projects, and they will appear here!</small>
                  </div>
                ) : (
                  filteredMemories.map((m) => (
                    <div className="memory-card" key={m.id}>
                      <div className="card-top">
                        <span className={`cat-badge cat-${m.category.toLowerCase()}`}>
                          <Tag size={10} /> {m.category}
                        </span>
                        <div className="card-meta">
                          <span className="confidence-badge">
                            {Math.round(m.confidence_score * 100)}%
                          </span>
                          <button
                            onClick={() => handleDeleteMemory(m.id)}
                            className="delete-mem-btn"
                            title="Delete this memory"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                      <div className="card-key">#{m.memory_key}</div>
                      <p className="card-content">{m.content}</p>
                    </div>
                  ))
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
