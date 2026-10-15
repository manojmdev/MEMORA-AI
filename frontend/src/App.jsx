import { useState, useEffect, useCallback } from "react";
import {
  BrainCircuit,
  Send,
  Sparkles,
  User,
  Trash2,
  Database,
  RefreshCw,
  Tag,
  Bot,
  Play,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldAlert,
  Clock,
  FileText,
  Check,
  Calculator,
  ListChecks,
} from "lucide-react";
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
  const [activeTab, setActiveTab] = useState("chat"); // 'chat' | 'agent'

  // Chat State
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

  // Agent State
  const [agentInput, setAgentInput] = useState("");
  const [agentRunning, setAgentRunning] = useState(false);
  const [activeTask, setActiveTask] = useState(null);
  const [taskReply, setTaskReply] = useState(null);
  const [memoriesUsed, setMemoriesUsed] = useState([]);
  const [toolsExecuted, setToolsExecuted] = useState([]);
  const [executionTimeline, setExecutionTimeline] = useState([]);
  const [recentTasks, setRecentTasks] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [agentError, setAgentError] = useState(null);

  // Fetch Memories
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

  // Fetch Notes
  const fetchNotes = useCallback(async () => {
    if (!sessionId) return;
    setLoadingNotes(true);
    try {
      const res = await fetch(`${API_URL}/api/notes?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const data = await res.json();
        setNotes(data.notes || []);
      }
    } catch (err) {
      console.error("Failed to fetch notes:", err);
    } finally {
      setLoadingNotes(false);
    }
  }, [sessionId]);

  // Fetch Recent Agent Tasks
  const fetchRecentTasks = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${API_URL}/api/agent/tasks?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const data = await res.json();
        setRecentTasks(data || []);
      }
    } catch (err) {
      console.error("Failed to fetch tasks:", err);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchMemories();
    fetchNotes();
    fetchRecentTasks();
  }, [fetchMemories, fetchNotes, fetchRecentTasks]);

  // Reset Session
  function handleResetSession() {
    const newId = "session_" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("memora_session_id", newId);
    setSessionId(newId);
    setActiveTask(null);
    setTaskReply(null);
    setExecutionTimeline([]);
    setMessages([
      {
        role: "assistant",
        content: `Switched to a fresh isolated session (${newId}). No memories or agent data from previous sessions will be accessed.`
      }
    ]);
  }

  // Chat Handler
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

  // Delete Memory
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

  // Clear All Memories
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

  // Agent Task Run
  async function handleRunAgentTask(customMsg) {
    const message = (typeof customMsg === "string" ? customMsg : agentInput).trim();
    if (!message || agentRunning) return;

    setAgentRunning(true);
    setAgentError(null);
    setTaskReply(null);
    setMemoriesUsed([]);
    setToolsExecuted([]);
    setExecutionTimeline([]);

    try {
      const res = await fetch(`${API_URL}/api/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Agent task failed.");
      }
      setActiveTask(data.task);
      setTaskReply(data.reply);
      setMemoriesUsed(data.memories_used || []);
      setToolsExecuted(data.tools_executed || []);
      setExecutionTimeline(data.execution_timeline || []);
      setAgentInput("");
      fetchNotes();
      fetchRecentTasks();
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setAgentRunning(false);
    }
  }

  // Approve Pending Action
  async function handleApproveTask(taskId, token) {
    if (!taskId || !token || actionLoading) return;
    setActionLoading(true);
    setAgentError(null);

    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${taskId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, approval_token: token })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Approval resumption failed.");
      }
      setActiveTask(data.task);
      setTaskReply(data.reply);
      setMemoriesUsed(data.memories_used || []);
      setToolsExecuted(data.tools_executed || []);
      setExecutionTimeline(data.execution_timeline || []);
      fetchNotes();
      fetchRecentTasks();
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  // Reject Pending Action
  async function handleRejectTask(taskId, token) {
    if (!taskId || actionLoading) return;
    setActionLoading(true);
    setAgentError(null);

    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${taskId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, approval_token: token })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Rejection handling failed.");
      }
      setActiveTask(data.task);
      setTaskReply(data.reply);
      fetchRecentTasks();
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  // Delete Note
  async function handleDeleteNote(noteId) {
    try {
      const res = await fetch(`${API_URL}/api/notes/${noteId}?session_id=${encodeURIComponent(sessionId)}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setNotes((prev) => prev.filter((n) => n.id !== noteId));
      }
    } catch (err) {
      console.error("Failed to delete note:", err);
    }
  }

  // Select Prior Task
  async function handleSelectTask(task) {
    setActiveTask(task);
    setTaskReply(task.result_summary || null);
    setAgentError(null);
    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${task.id}/logs?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const logs = await res.json();
        setExecutionTimeline(
          logs.map((l) => ({
            step_id: l.step_id,
            tool_name: l.tool_name,
            status: l.status,
            result_summary: l.result_summary,
            duration_ms: l.duration_ms
          }))
        );
      }
    } catch (err) {
      console.error("Failed to fetch task logs:", err);
    }
  }

  const filteredMemories = memories.filter((m) => {
    if (selectedCategory === "all") return true;
    return m.category.toLowerCase() === selectedCategory.toLowerCase();
  });

  const categories = ["all", ...new Set(memories.map((m) => m.category.toLowerCase()))];

  return (
    <div className="app-shell">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="brand">
          <div className="brand-icon">
            <BrainCircuit size={23} />
          </div>
          <div>
            <h2>MEMORA<span> AI</span></h2>
            <p>Day 6 · Controlled Agentic Memory & Execution</p>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div className="tab-switcher">
          <button
            className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            <BrainCircuit size={15} />
            <span>Chat & Memory</span>
          </button>
          <button
            className={`tab-btn ${activeTab === "agent" ? "active" : ""}`}
            onClick={() => setActiveTab("agent")}
          >
            <Bot size={15} />
            <span>Agent Workspace</span>
            {recentTasks.length > 0 && <span className="tab-badge">{recentTasks.length}</span>}
          </button>
        </div>

        <div className="nav-actions">
          {activeTab === "chat" && (
            <button
              className={`panel-toggle-btn ${showMemoryPanel ? "active" : ""}`}
              onClick={() => setShowMemoryPanel(!showMemoryPanel)}
              title="Toggle Memory Panel"
            >
              <Database size={16} />
              <span>Memories ({memories.length})</span>
            </button>
          )}

          <div className="connection">
            <span className="status-dot"></span>
            <span>Neon pgvector + Nemotron Agent</span>
          </div>
        </div>
      </header>

      <main className="workspace">
        {/* Banner Section */}
        <section className="welcome">
          <div className="sparkle">
            <Sparkles size={22} />
          </div>
          <p className="eyebrow">
            {activeTab === "chat" ? "PERSISTENT MEMORY EVOLUTION ENGINE" : "DAY 6 AGENTIC MEMORY & CONTROLLED EXECUTION"}
          </p>
          <h1>
            {activeTab === "chat" ? (
              <>
                Intelligence that
                <br />
                <span>remembers & evolves.</span>
              </>
            ) : (
              <>
                Agentic Execution with
                <br />
                <span>permission gates & memory recall.</span>
              </>
            )}
          </h1>
          <p className="subtitle">
            {activeTab === "chat"
              ? "Powered by NVIDIA Nemotron and Neon Lakebase Postgres."
              : "Autonomous planning with backend-enforced permissions, human-in-the-loop approval, and strict session isolation."}
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

        {/* TAB 1: CHAT & MEMORY */}
        {activeTab === "chat" && (
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
                        <div className="memories-used-panel">
                          <div className="memories-used-header">
                            <Sparkles size={12} className="sparkle-icon" />
                            <span>MEMORIES USED</span>
                            <span className="count-badge">{msg.recalled.length}</span>
                          </div>
                          <div className="memories-used-list">
                            {msg.recalled.map((rec, i) => (
                              <div key={i} className="memory-used-item">
                                <div className="used-item-top">
                                  <span className={`method-badge method-${rec.retrieval_method || "keyword"}`}>
                                    {rec.retrieval_method === "hybrid" && "✨ Hybrid"}
                                    {rec.retrieval_method === "semantic" && "🧠 Semantic"}
                                    {rec.retrieval_method === "keyword" && "🔍 Keyword"}
                                  </span>
                                  <span className="used-key">#{rec.memory_key}</span>
                                  {rec.similarity_score !== undefined && (
                                    <span className="score-badge" title="Retriever similarity score">
                                      {Math.round(rec.similarity_score * 100)}% match
                                    </span>
                                  )}
                                </div>
                                <p className="used-content">{rec.content}</p>
                                {rec.retrieval_reason && (
                                  <div className="used-reason">
                                    <span className="reason-label">Why retrieved:</span> {rec.retrieval_reason}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
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
                          <div className="card-top-tags">
                            <span className={`cat-badge cat-${m.category.toLowerCase()}`}>
                              <Tag size={10} /> {m.category}
                            </span>
                            <span className={`badge-pill ${m.persistence_type === "temporary" ? "badge-temporary" : "badge-persistent"}`}>
                              {m.persistence_type === "temporary" ? "⏳ Temporary" : "📌 Persistent"}
                            </span>
                            <span className={`badge-pill ${m.information_source === "contextual_inference" ? "badge-source-inferred" : "badge-source-explicit"}`}>
                              {m.information_source === "contextual_inference" ? "Inferred" : "Explicit"}
                            </span>
                          </div>
                          <div className="card-meta">
                            <span className="confidence-badge" title="Confidence score">
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
                        <div className="card-key">
                          #{m.memory_key}
                          {m.has_embedding && <span className="vector-badge" title="Vector embedded in Neon pgvector">⚡ pgvector</span>}
                        </div>
                        <p className="card-content">{m.content}</p>
                        {m.reason_for_storage && (
                          <div className="card-reason" title="Reason for storage">
                            💡 <small>{m.reason_for_storage}</small>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </aside>
            )}
          </div>
        )}

        {/* TAB 2: AGENT WORKSPACE */}
        {activeTab === "agent" && (
          <div className="agent-workspace-grid">
            {/* Left: Agent Execution Center */}
            <section className="agent-main-panel">
              {/* Task Prompt Input */}
              <div className="agent-prompt-card">
                <div className="agent-prompt-header">
                  <div className="agent-prompt-title">
                    <Bot size={18} className="bot-icon" />
                    <span>Agentic Task Dispatcher</span>
                  </div>
                  <span className="agent-policy-badge">Policy: Backend Governed</span>
                </div>

                <div className="agent-input-container">
                  <textarea
                    rows={3}
                    value={agentInput}
                    onChange={(e) => setAgentInput(e.target.value)}
                    placeholder="Enter an agent task (e.g., 'Generate a Python study plan using my memories and save it as a note', 'Calculate 24 * 365 + 100', 'List my active goals')..."
                    disabled={agentRunning}
                  />
                  <div className="agent-prompt-actions">
                    <button
                      className="run-task-btn"
                      onClick={() => handleRunAgentTask()}
                      disabled={agentRunning || !agentInput.trim()}
                    >
                      {agentRunning ? (
                        <>
                          <RefreshCw size={15} className="spin" /> Executing Plan...
                        </>
                      ) : (
                        <>
                          <Play size={15} /> Execute Task
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Quick Task Starters */}
                <div className="task-starters">
                  <span className="starters-label">Try task:</span>
                  <button
                    className="starter-btn"
                    onClick={() =>
                      handleRunAgentTask(
                        "Check my memories for programming preferences, generate a 3-week study plan, and save it as a persistent note."
                      )
                    }
                  >
                    📝 Study plan + Persistent Note
                  </button>
                  <button
                    className="starter-btn"
                    onClick={() =>
                      handleRunAgentTask(
                        "Calculate (1024 * 768 * 4) / 1000000 to find the uncompressed frame size in megabytes."
                      )
                    }
                  >
                    🔢 Safe Calculator
                  </button>
                  <button
                    className="starter-btn"
                    onClick={() =>
                      handleRunAgentTask("Search my memories for my current projects and technical skills.")
                    }
                  >
                    🔍 Memory Inspection
                  </button>
                </div>
              </div>

              {agentError && (
                <div className="agent-error-alert">
                  <AlertTriangle size={18} />
                  <span>{agentError}</span>
                </div>
              )}

              {/* Active Task Plan & Approval Center */}
              {activeTask && (
                <div className="agent-task-details-card">
                  {/* Task Header */}
                  <div className="task-header-row">
                    <div>
                      <span className="task-sub">TASK #{activeTask.id.slice(0, 8)}</span>
                      <h3 className="task-objective">{activeTask.plan?.objective || activeTask.user_request}</h3>
                    </div>
                    <div className="task-status-container">
                      <span className={`status-pill status-${activeTask.status}`}>
                        {activeTask.status === "awaiting_approval" && "⚠️ Awaiting Approval"}
                        {activeTask.status === "succeeded" && "✅ Succeeded"}
                        {activeTask.status === "running" && "⚡ Running"}
                        {activeTask.status === "failed" && "❌ Failed"}
                        {activeTask.status === "cancelled" && "🚫 Cancelled"}
                        {activeTask.status === "proposed" && "📋 Proposed"}
                      </span>
                    </div>
                  </div>

                  {/* HUMAN-IN-THE-LOOP APPROVAL CARD */}
                  {activeTask.status === "awaiting_approval" && activeTask.pending_approval && (
                    <div className="approval-gate-card">
                      <div className="approval-gate-header">
                        <div className="gate-title-box">
                          <ShieldAlert size={20} className="gate-icon" />
                          <div>
                            <h4>Human-in-the-Loop Approval Required</h4>
                            <p>An operation is requesting to modify persistent database records.</p>
                          </div>
                        </div>
                        <span className="gate-badge">Tool: {activeTask.pending_approval.operation}</span>
                      </div>

                      <div className="approval-payload-preview">
                        <div className="preview-field">
                          <span className="field-label">Target Operation:</span>
                          <span className="field-val">Persistent Note Insertion</span>
                        </div>
                        <div className="preview-field">
                          <span className="field-label">Title:</span>
                          <span className="field-val highlight">{activeTask.pending_approval.title}</span>
                        </div>
                        <div className="preview-field">
                          <span className="field-label">Content Preview:</span>
                          <p className="preview-content-box">{activeTask.pending_approval.content}</p>
                        </div>
                        <div className="preview-field">
                          <span className="field-label">Consequences:</span>
                          <span className="field-val warn">{activeTask.pending_approval.consequences}</span>
                        </div>
                      </div>

                      <div className="approval-actions-bar">
                        <button
                          className="approve-btn"
                          onClick={() =>
                            handleApproveTask(
                              activeTask.id,
                              activeTask.approval_token || activeTask.pending_approval.approval_token
                            )
                          }
                          disabled={actionLoading}
                        >
                          <Check size={16} />
                          {actionLoading ? "Processing Approval..." : "Approve & Execute"}
                        </button>
                        <button
                          className="reject-btn"
                          onClick={() =>
                            handleRejectTask(
                              activeTask.id,
                              activeTask.approval_token || activeTask.pending_approval.approval_token
                            )
                          }
                          disabled={actionLoading}
                        >
                          <XCircle size={16} />
                          {actionLoading ? "Rejecting..." : "Reject & Cancel"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Plan Steps List */}
                  {activeTask.plan && activeTask.plan.steps && (
                    <div className="plan-steps-section">
                      <h4 className="section-title">
                        <ListChecks size={16} />
                        Plan Steps ({activeTask.plan.steps.length})
                      </h4>
                      <div className="steps-list">
                        {activeTask.plan.steps.map((step, idx) => (
                          <div className={`step-item step-${step.status}`} key={step.step_id || idx}>
                            <div className="step-left">
                              <span className="step-idx">{idx + 1}</span>
                              <div className="step-body">
                                <div className="step-title-line">
                                  <span className="step-id">{step.step_id}</span>
                                  <span className="step-desc">{step.description}</span>
                                </div>
                                <div className="step-meta-row">
                                  {step.tool_name && (
                                    <span className="step-tool-badge">
                                      🔧 {step.tool_name}
                                    </span>
                                  )}
                                  <span
                                    className={`step-perm-badge perm-${step.permission}`}
                                  >
                                    {step.permission === "automatic" ? "⚡ AUTOMATIC" : "🛡️ APPROVAL REQUIRED"}
                                  </span>
                                </div>
                              </div>
                            </div>

                            <div className="step-right">
                              <span className={`step-state-badge state-${step.status}`}>
                                {step.status === "succeeded" && <CheckCircle2 size={14} />}
                                {step.status === "awaiting_approval" && <Clock size={14} />}
                                {step.status === "running" && <RefreshCw size={14} className="spin" />}
                                {step.status === "pending" && <Clock size={14} />}
                                {step.status === "cancelled" && <XCircle size={14} />}
                                <span>{step.status}</span>
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Synthesized Response Output */}
                  {taskReply && (
                    <div className="agent-result-box">
                      <div className="result-header">
                        <div className="result-header-left">
                          <Sparkles size={16} className="sparkle-icon" />
                          <h4>Agent Execution Output</h4>
                        </div>
                        {toolsExecuted.length > 0 && (
                          <div className="tools-executed-tags">
                            {toolsExecuted.map((t, i) => (
                              <span key={i} className="tool-tag">
                                ⚙️ {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="result-content-text">
                        <p>{taskReply}</p>
                      </div>

                      {memoriesUsed.length > 0 && (
                        <div className="memories-recalled-summary">
                          <span className="recalled-label">Memories Integrated:</span>
                          {memoriesUsed.map((m, i) => (
                            <span key={i} className="mem-item-pill">
                              #{m.memory_key}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Execution Timeline */}
                  {executionTimeline.length > 0 && (
                    <div className="execution-timeline-section">
                      <h4 className="section-title">
                        <Clock size={16} /> Audit Execution Timeline
                      </h4>
                      <div className="timeline-items">
                        {executionTimeline.map((item, i) => (
                          <div className="timeline-row" key={i}>
                            <span className="timeline-dot"></span>
                            <div className="timeline-body">
                              <div className="timeline-top">
                                <span className="timeline-tool">{item.tool_name}</span>
                                <span className="timeline-step">({item.step_id})</span>
                                {item.duration_ms !== undefined && item.duration_ms !== null && (
                                  <span className="timeline-ms">{item.duration_ms}ms</span>
                                )}
                              </div>
                              {item.result_summary && (
                                <p className="timeline-summary">{item.result_summary}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* Right: Notes Storage & Task History Panel */}
            <aside className="agent-sidebar">
              {/* Notes Storage */}
              <div className="sidebar-card">
                <div className="sidebar-header">
                  <div className="sidebar-title">
                    <FileText size={16} className="note-icon" />
                    <div>
                      <h4>Persistent Notes</h4>
                      <small>{notes.length} note{notes.length === 1 ? "" : "s"} saved</small>
                    </div>
                  </div>
                  <button
                    onClick={fetchNotes}
                    className="icon-btn"
                    title="Refresh notes"
                    disabled={loadingNotes}
                  >
                    <RefreshCw size={13} className={loadingNotes ? "spin" : ""} />
                  </button>
                </div>

                <div className="notes-list">
                  {notes.length === 0 ? (
                    <div className="empty-sidebar-box">
                      <FileText size={22} />
                      <p>No persistent notes yet.</p>
                      <small>Ask the agent to create and save a note for you!</small>
                    </div>
                  ) : (
                    notes.map((note) => (
                      <div className="note-card" key={note.id}>
                        <div className="note-top">
                          <h5 className="note-title">{note.title}</h5>
                          <button
                            className="delete-note-btn"
                            onClick={() => handleDeleteNote(note.id)}
                            title="Delete note"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                        <p className="note-content">{note.content}</p>
                        <span className="note-date">
                          {new Date(note.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit"
                          })}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Task History */}
              <div className="sidebar-card">
                <div className="sidebar-header">
                  <div className="sidebar-title">
                    <Clock size={16} className="history-icon" />
                    <div>
                      <h4>Recent Tasks</h4>
                      <small>{recentTasks.length} task{recentTasks.length === 1 ? "" : "s"}</small>
                    </div>
                  </div>
                  <button
                    onClick={fetchRecentTasks}
                    className="icon-btn"
                    title="Refresh task history"
                  >
                    <RefreshCw size={13} />
                  </button>
                </div>

                <div className="tasks-history-list">
                  {recentTasks.length === 0 ? (
                    <div className="empty-sidebar-box">
                      <Bot size={22} />
                      <p>No recent tasks.</p>
                    </div>
                  ) : (
                    recentTasks.map((t) => (
                      <div
                        className={`history-task-item ${activeTask?.id === t.id ? "active" : ""}`}
                        key={t.id}
                        onClick={() => handleSelectTask(t)}
                      >
                        <div className="history-task-top">
                          <span className={`status-dot-sm status-${t.status}`}></span>
                          <span className="history-task-req">{t.user_request}</span>
                        </div>
                        <div className="history-task-meta">
                          <span className="history-task-status">{t.status}</span>
                          <span className="history-task-time">
                            {new Date(t.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit"
                            })}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
