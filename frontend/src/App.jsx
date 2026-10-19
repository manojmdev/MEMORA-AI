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
  Activity,
  Network,
  Layers,
  Archive,
  Eye,
  Zap,
  ArrowRight,
  ShieldCheck,
  X,
  Plus,
  Compass,
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
  const [taskCheckpoints, setTaskCheckpoints] = useState([]);
  const [showCheckpoints, setShowCheckpoints] = useState(false);

  // Sprint 2: Memory Intelligence 2.0 State
  const [dashboardStats, setDashboardStats] = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [selectedGraphNode, setSelectedGraphNode] = useState(null);
  const [intelligenceSubTab, setIntelligenceSubTab] = useState("graph"); // "graph" | "consolidation" | "retrieval" | "lifecycle"

  // Consolidation State
  const [consolidationPreview, setConsolidationPreview] = useState(null);
  const [loadingConsolidation, setLoadingConsolidation] = useState(false);
  const [applyingConsolidation, setApplyingConsolidation] = useState(false);
  const [consolidationStatusMsg, setConsolidationStatusMsg] = useState(null);

  // Explainability Modal State
  const [explainData, setExplainData] = useState(null);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [showExplainModal, setShowExplainModal] = useState(false);

  // Add Relationship Modal State
  const [showRelModal, setShowRelModal] = useState(false);
  const [relSourceId, setRelSourceId] = useState("");
  const [relTargetId, setRelTargetId] = useState("");
  const [relType, setRelType] = useState("uses");
  const [relStrength, setRelStrength] = useState(1.0);

  // Retrieval 2.0 State
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalResults, setRetrievalResults] = useState([]);
  const [loadingRetrieval, setLoadingRetrieval] = useState(false);

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

  // Fetch Dashboard Stats
  const fetchDashboardStats = useCallback(async () => {
    if (!sessionId) return;
    setLoadingDashboard(true);
    try {
      const res = await fetch(`${API_URL}/api/memories/dashboard?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const data = await res.json();
        setDashboardStats(data);
      }
    } catch (err) {
      console.error("Failed to fetch dashboard stats:", err);
    } finally {
      setLoadingDashboard(false);
    }
  }, [sessionId]);

  // Fetch Relationship Graph
  const fetchGraphData = useCallback(async () => {
    if (!sessionId) return;
    setLoadingGraph(true);
    try {
      const res = await fetch(`${API_URL}/api/memories/graph?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const data = await res.json();
        setGraphData(data);
      }
    } catch (err) {
      console.error("Failed to fetch graph data:", err);
    } finally {
      setLoadingGraph(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchMemories();
    fetchNotes();
    fetchRecentTasks();
    fetchDashboardStats();
    fetchGraphData();
  }, [fetchMemories, fetchNotes, fetchRecentTasks, fetchDashboardStats, fetchGraphData]);

  // Reset Session
  function handleResetSession() {
    const newId = "session_" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("memora_session_id", newId);
    setSessionId(newId);
    setActiveTask(null);
    setTaskReply(null);
    setExecutionTimeline([]);
    setDashboardStats(null);
    setGraphData({ nodes: [], edges: [] });
    setConsolidationPreview(null);
    setRetrievalResults([]);
    setMessages([
      {
        role: "assistant",
        content: `Switched to a fresh isolated session (${newId}). No memories or agent data from previous sessions will be accessed.`
      }
    ]);
  }

  // Preview Consolidation
  async function handlePreviewConsolidation() {
    setLoadingConsolidation(true);
    setConsolidationStatusMsg(null);
    try {
      const res = await fetch(
        `${API_URL}/api/memories/consolidation/preview?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST" }
      );
      if (res.ok) {
        const data = await res.json();
        setConsolidationPreview(data);
        if (!data.candidate_groups || data.candidate_groups.length === 0) {
          setConsolidationStatusMsg("No overlapping or duplicate memories detected for consolidation.");
        }
      }
    } catch (err) {
      console.error("Consolidation preview failed:", err);
    } finally {
      setLoadingConsolidation(false);
    }
  }

  // Apply Consolidation
  async function handleApplyConsolidation(candidate) {
    setApplyingConsolidation(true);
    try {
      const res = await fetch(`${API_URL}/api/memories/consolidation/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          source_memory_ids: candidate.source_memory_ids,
          consolidated_content: candidate.proposed_consolidated_content,
          cluster_topic: candidate.cluster_topic,
          rationale: candidate.consolidation_rationale
        })
      });
      if (res.ok) {
        setConsolidationStatusMsg(`Successfully consolidated ${candidate.source_memory_ids.length} memories into "${candidate.cluster_topic}"!`);
        setConsolidationPreview((prev) =>
          prev ? { ...prev, candidate_groups: prev.candidate_groups.filter((g) => g.cluster_topic !== candidate.cluster_topic) } : null
        );
        fetchMemories();
        fetchDashboardStats();
        fetchGraphData();
      }
    } catch (err) {
      console.error("Apply consolidation failed:", err);
    } finally {
      setApplyingConsolidation(false);
    }
  }

  // Explain Memory
  async function handleExplainMemory(memoryId) {
    setLoadingExplain(true);
    setShowExplainModal(true);
    try {
      const res = await fetch(
        `${API_URL}/api/memories/${memoryId}/explain?session_id=${encodeURIComponent(sessionId)}`
      );
      if (res.ok) {
        const data = await res.json();
        setExplainData(data);
      }
    } catch (err) {
      console.error("Failed to explain memory:", err);
    } finally {
      setLoadingExplain(false);
    }
  }

  // Archive Memory
  async function handleArchiveMemory(memoryId) {
    try {
      const res = await fetch(
        `${API_URL}/api/memories/${memoryId}/archive?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST" }
      );
      if (res.ok) {
        fetchMemories();
        fetchDashboardStats();
        if (explainData?.memory_id === memoryId) {
          handleExplainMemory(memoryId);
        }
      }
    } catch (err) {
      console.error("Failed to archive memory:", err);
    }
  }

  // Restore Memory
  async function handleRestoreMemory(memoryId) {
    try {
      const res = await fetch(
        `${API_URL}/api/memories/${memoryId}/restore?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST" }
      );
      if (res.ok) {
        fetchMemories();
        fetchDashboardStats();
        if (explainData?.memory_id === memoryId) {
          handleExplainMemory(memoryId);
        }
      }
    } catch (err) {
      console.error("Failed to restore memory:", err);
    }
  }

  // Forget Memory (Vector wipe & Deactivate)
  async function handleForgetMemory(memoryId) {
    if (!window.confirm("Immediately remove memory from active retrieval and completely purge its vector embedding?")) return;
    try {
      const res = await fetch(
        `${API_URL}/api/memories/${memoryId}/forget?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST" }
      );
      if (res.ok) {
        setShowExplainModal(false);
        fetchMemories();
        fetchDashboardStats();
        fetchGraphData();
      }
    } catch (err) {
      console.error("Failed to forget memory:", err);
    }
  }

  // Create Relationship
  async function handleCreateRelationship() {
    if (!relSourceId || !relTargetId || relSourceId === relTargetId) return;
    try {
      const res = await fetch(`${API_URL}/api/memories/relationships`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          source_memory_id: relSourceId,
          target_memory_id: relTargetId,
          relationship_type: relType,
          strength: parseFloat(relStrength) || 1.0,
          metadata: {}
        })
      });
      if (res.ok) {
        setShowRelModal(false);
        setRelSourceId("");
        setRelTargetId("");
        fetchGraphData();
        fetchDashboardStats();
      }
    } catch (err) {
      console.error("Failed to create relationship:", err);
    }
  }

  // Delete Relationship
  async function handleDeleteRelationship(relId) {
    try {
      const res = await fetch(
        `${API_URL}/api/memories/relationships/${relId}?session_id=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        fetchGraphData();
        fetchDashboardStats();
      }
    } catch (err) {
      console.error("Failed to delete relationship:", err);
    }
  }

  // Check Retention Policy
  async function handleCheckRetention() {
    try {
      const res = await fetch(
        `${API_URL}/api/memories/retention/check?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST" }
      );
      if (res.ok) {
        const data = await res.json();
        alert(`Retention Policy Evaluated: ${data.expired_count} memories expired.`);
        fetchMemories();
        fetchDashboardStats();
      }
    } catch (err) {
      console.error("Failed to check retention:", err);
    }
  }

  // Run Retrieval 2.0 Test
  async function handleRunRetrievalTest() {
    if (!retrievalQuery.trim()) return;
    setLoadingRetrieval(true);
    try {
      const res = await fetch(
        `${API_URL}/api/memories/search/v2?session_id=${encodeURIComponent(sessionId)}&query=${encodeURIComponent(retrievalQuery)}&limit=5&debug_scores=true`
      );
      if (res.ok) {
        const data = await res.json();
        setRetrievalResults(data);
      }
    } catch (err) {
      console.error("Failed to run retrieval test:", err);
    } finally {
      setLoadingRetrieval(false);
    }
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
      if (data.task?.id) {
        fetchTaskCheckpoints(data.task.id);
      }
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
      if (data.task?.id) {
        fetchTaskCheckpoints(data.task.id);
      }
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  // Cancel Task
  async function handleCancelTask(taskId) {
    if (!taskId || actionLoading) return;
    setActionLoading(true);
    setAgentError(null);

    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${taskId}/cancel?session_id=${encodeURIComponent(sessionId)}`, {
        method: "POST"
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Task cancellation failed.");
      }
      setActiveTask(data.task);
      setTaskReply(data.reply);
      fetchRecentTasks();
      fetchTaskCheckpoints(taskId);
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  // Retry Task
  async function handleRetryTask(taskId) {
    if (!taskId || actionLoading) return;
    setActionLoading(true);
    setAgentError(null);

    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${taskId}/retry?session_id=${encodeURIComponent(sessionId)}`, {
        method: "POST"
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Task retry failed.");
      }
      setActiveTask(data.task);
      setTaskReply(data.reply);
      setMemoriesUsed(data.memories_used || []);
      setToolsExecuted(data.tools_executed || []);
      setExecutionTimeline(data.execution_timeline || []);
      fetchNotes();
      fetchRecentTasks();
      fetchTaskCheckpoints(taskId);
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  // Fetch Checkpoints for Task
  async function fetchTaskCheckpoints(taskId) {
    if (!taskId) return;
    try {
      const res = await fetch(`${API_URL}/api/agent/tasks/${taskId}/checkpoints?session_id=${encodeURIComponent(sessionId)}`);
      if (res.ok) {
        const cps = await res.json();
        setTaskCheckpoints(cps || []);
      }
    } catch (err) {
      console.error("Failed to fetch task checkpoints:", err);
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
    fetchTaskCheckpoints(task.id);
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
            <p>Sprint 2 · Advanced Memory Intelligence 2.0</p>
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
          <button
            className={`tab-btn ${activeTab === "intelligence" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("intelligence");
              fetchDashboardStats();
              fetchGraphData();
            }}
          >
            <Activity size={15} />
            <span>Intelligence 2.0</span>
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
            <span>Neon pgvector + Nemotron</span>
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
            {activeTab === "chat"
              ? "PERSISTENT MEMORY EVOLUTION ENGINE"
              : activeTab === "agent"
              ? "DAY 6 AGENTIC MEMORY & CONTROLLED EXECUTION"
              : "ADVANCED MEMORY INTELLIGENCE 2.0"}
          </p>
          <h1>
            {activeTab === "chat" ? (
              <>
                Intelligence that
                <br />
                <span>remembers & evolves.</span>
              </>
            ) : activeTab === "agent" ? (
              <>
                Agentic Execution with
                <br />
                <span>permission gates & memory recall.</span>
              </>
            ) : (
              <>
                Explainable Long-Term Memory
                <br />
                <span>with relationship graphs & consolidation.</span>
              </>
            )}
          </h1>
          <p className="subtitle">
            {activeTab === "chat"
              ? "Powered by NVIDIA Nemotron and Neon Lakebase Postgres."
              : activeTab === "agent"
              ? "Autonomous planning with backend-enforced permissions, human-in-the-loop approval, and strict session isolation."
              : "Deep knowledge graph relationships, automated duplicate consolidation with contradiction detection, multi-factor retrieval 2.0, and lifecycle governance."}
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
                              onClick={() => handleExplainMemory(m.id)}
                              className="explain-mem-btn"
                              title="Explain memory decision & lineage"
                            >
                              <Eye size={12} />
                            </button>
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
                        {activeTask.status === "needs_reconciliation" && "⚠️ Needs Reconciliation"}
                        {activeTask.status === "awaiting_clarification" && "❓ Awaiting Clarification"}
                      </span>
                    </div>
                  </div>

                  {/* Task Metadata Bar & Controls */}
                  <div className="task-meta-bar">
                    <span className={`meta-pill complexity-${activeTask.estimated_complexity || activeTask.plan?.estimated_complexity || 'low'}`}>
                      ⚡ Complexity: {(activeTask.estimated_complexity || activeTask.plan?.estimated_complexity || 'low').toUpperCase()}
                    </span>
                    <span className="meta-pill">
                      💎 Cost: {(activeTask.estimated_cost_tier || activeTask.plan?.estimated_cost_tier || 'standard').toUpperCase()}
                    </span>
                    {taskCheckpoints.length > 0 && (
                      <span className="meta-pill" style={{ cursor: "pointer", color: "#60a5fa" }} onClick={() => setShowCheckpoints(!showCheckpoints)}>
                        💾 Checkpoints ({taskCheckpoints.filter(c => c.status === "succeeded" || c.status === "completed").length}/{taskCheckpoints.length}) {showCheckpoints ? "▲" : "▼"}
                      </span>
                    )}
                    <div className="task-controls-row">
                      {(activeTask.status === "running" || activeTask.status === "awaiting_approval") && (
                        <button
                          className="btn-cancel-task"
                          onClick={() => handleCancelTask(activeTask.id)}
                          disabled={actionLoading}
                        >
                          Cancel Task
                        </button>
                      )}
                      {(activeTask.status === "failed" || activeTask.status === "needs_reconciliation") && (
                        <button
                          className="btn-retry-task"
                          onClick={() => handleRetryTask(activeTask.id)}
                          disabled={actionLoading}
                        >
                          Resume / Retry Task
                        </button>
                      )}
                    </div>
                  </div>

                  {/* State Reconciliation Alert */}
                  {activeTask.status === "needs_reconciliation" && (
                    <div className="reconciliation-warning-box">
                      <AlertTriangle size={20} color="#ef4444" />
                      <div>
                        <h4>State Reconciliation Required</h4>
                        <p>
                          A state-changing tool call was interrupted or encountered an ambiguous outcome. To protect data integrity, automatic retries have been paused. Please review persistent state or click &ldquo;Resume / Retry Task&rdquo; to re-attempt.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Task Ambiguity / Clarification Alert */}
                  {(activeTask.requires_clarification || activeTask.plan?.requires_clarification) && (
                    <div className="reconciliation-warning-box" style={{ background: "rgba(168, 85, 247, 0.12)", borderColor: "#a855f7" }}>
                      <AlertTriangle size={20} color="#a855f7" />
                      <div>
                        <h4 style={{ color: "#d8b4fe" }}>Task Ambiguity Detected — Clarification Requested</h4>
                        <p style={{ color: "#e9d5ff" }}>
                          {activeTask.clarification_prompt || activeTask.plan?.clarification_prompt || "The objective requires more detail before execution."}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* DAG Execution Topology */}
                  {activeTask.plan?.steps && activeTask.plan.steps.length > 0 && (
                    <div className="dag-section">
                      <h4 className="section-title">
                        <Network size={16} /> DAG Execution Topology ({activeTask.plan.steps.length} Nodes{activeTask.plan.dag_edges?.length ? `, ${activeTask.plan.dag_edges.length} Edges` : ""})
                      </h4>
                      <div className="dag-nodes-grid">
                        {activeTask.plan.steps.map((st, i) => (
                          <div key={st.step_id || i} className={`dag-node-box status-${st.status}`}>
                            <div className="dag-node-header">
                              <span className="dag-node-id">{st.step_id}</span>
                              <span className={`step-state-badge state-${st.status}`}>{st.status}</span>
                            </div>
                            <div className="dag-node-deps">
                              {st.dependencies && st.dependencies.length > 0
                                ? `Depends on: ${st.dependencies.join(", ")}`
                                : "Root (Independent)"}
                            </div>
                            <div style={{ fontSize: "10px", color: st.is_idempotent !== false ? "#86efac" : "#fca5a5" }}>
                              {st.is_idempotent !== false ? "⚡ Idempotent" : "📝 State-Changing"}
                              {st.retry_count > 0 ? ` (Retry: ${st.retry_count})` : ""}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Collapsible Durable Checkpoints View */}
                  {showCheckpoints && taskCheckpoints.length > 0 && (
                    <div className="plan-steps-section" style={{ background: "#0c1322", padding: "14px", borderRadius: "10px", border: "1px solid #1e293b" }}>
                      <h4 className="section-title">
                        <Database size={16} /> Durable PostgreSQL Checkpoints
                      </h4>
                      <div className="steps-list">
                        {taskCheckpoints.map((cp, idx) => (
                          <div className={`step-item step-${cp.status}`} key={cp.id || idx}>
                            <div className="step-left">
                              <span className="step-idx">{idx + 1}</span>
                              <div className="step-body">
                                <div className="step-title-line">
                                  <span className="step-id">{cp.step_id}</span>
                                  <span className="step-desc">Tool: {cp.tool_name}</span>
                                </div>
                                <div className="step-meta-row">
                                  <span className="step-tool-badge">Key: {cp.idempotency_key?.slice(0, 10)}...</span>
                                  {cp.retry_count > 0 && <span className="step-tool-badge">Retries: {cp.retry_count}/{cp.max_retries}</span>}
                                  {cp.error_classification && <span className="step-tool-badge" style={{ color: "#fca5a5" }}>Error: {cp.error_classification}</span>}
                                </div>
                              </div>
                            </div>
                            <div className="step-right">
                              <span className={`step-state-badge state-${cp.status}`}>
                                {cp.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Memory Influences Section */}
                  {activeTask.plan?.memory_influences && activeTask.plan.memory_influences.length > 0 && (
                    <div className="memory-influences-section">
                      <h4 className="section-title">
                        <Sparkles size={16} /> Memory Influences ({activeTask.plan.memory_influences.length})
                      </h4>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 8px" }}>
                        Memories that actively shaped the generated execution plan:
                      </p>
                      {activeTask.plan.memory_influences.map((inf, i) => (
                        <div className="influence-card" key={i}>
                          <div>
                            <span style={{ fontSize: "12px", fontWeight: "600", color: "#e2e8f0" }}>
                              {inf.category?.toUpperCase() || "FACT"}
                            </span>
                            <span style={{ fontSize: "12px", color: "#94a3b8", marginLeft: "8px" }}>
                              {inf.content}
                            </span>
                          </div>
                          <div>
                            <span className={inf.is_inferred ? "influence-badge-inferred" : "influence-badge-explicit"}>
                              {inf.is_inferred ? "Inferred Context" : "Explicit Fact"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

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

                      {(() => {
                        const token = activeTask.approval_token || activeTask.pending_approval?.approval_token;
                        const hasToken = token && !token.includes("[REDACTED");
                        return (
                          <>
                            {!hasToken && (
                              <div className="historical-token-notice" style={{ padding: "0.75rem 1rem", background: "rgba(234, 179, 8, 0.1)", border: "1px solid rgba(234, 179, 8, 0.3)", borderRadius: "8px", marginBottom: "0.75rem", fontSize: "0.82rem", color: "#eab308" }}>
                                ℹ️ This task was reloaded from session history. In accordance with zero-knowledge token security, approval tokens are never stored or exposed in task history. Please re-run the task to generate a fresh approval token.
                              </div>
                            )}
                            <div className="approval-actions-bar">
                              <button
                                className="approve-btn"
                                onClick={() => handleApproveTask(activeTask.id, token)}
                                disabled={actionLoading || !hasToken}
                                title={!hasToken ? "Approval tokens are not retained in history for security" : "Approve and execute"}
                              >
                                <Check size={16} />
                                {actionLoading ? "Processing Approval..." : "Approve & Execute"}
                              </button>
                              <button
                                className="reject-btn"
                                onClick={() => handleRejectTask(activeTask.id, token)}
                                disabled={actionLoading}
                              >
                                <XCircle size={16} />
                                {actionLoading ? "Rejecting..." : "Reject & Cancel"}
                              </button>
                            </div>
                          </>
                        );
                      })()}
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

        {/* TAB 3: ADVANCED MEMORY INTELLIGENCE 2.0 */}
        {activeTab === "intelligence" && (
          <div className="intelligence-workspace">
            {/* Top KPI Metrics Bar */}
            <div className="intelligence-kpi-grid">
              <div className="kpi-card">
                <div className="kpi-label">Active Memories</div>
                <div className="kpi-value">
                  {dashboardStats?.active_memories ?? memories.length}
                  <span className="kpi-sub"> / {dashboardStats?.total_memories ?? memories.length} total</span>
                </div>
                <div className="kpi-foot">
                  <span>Archived: {dashboardStats?.archived_memories ?? 0}</span>
                  <span>Expired: {dashboardStats?.expired_memories ?? 0}</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">Temporal Split</div>
                <div className="kpi-value">
                  {dashboardStats?.persistent_count ?? 0}
                  <span className="kpi-sub"> persistent</span>
                </div>
                <div className="kpi-foot">
                  <span>Temporary (TTL): {dashboardStats?.temporary_count ?? 0}</span>
                  <button className="retention-btn" onClick={handleCheckRetention} title="Evaluate temporal TTL retention">
                    <Clock size={11} /> Check TTL
                  </button>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">Relationship Graph</div>
                <div className="kpi-value">
                  {dashboardStats?.relationship_count ?? (graphData.edges?.length || 0)}
                  <span className="kpi-sub"> typed edges</span>
                </div>
                <div className="kpi-foot">
                  <span>Across {graphData.nodes?.length || memories.length} memory nodes</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">Consolidation Engine</div>
                <div className="kpi-value">
                  {dashboardStats?.consolidation_count ?? 0}
                  <span className="kpi-sub"> merged</span>
                </div>
                <div className="kpi-foot">
                  <span>Overlaps detected: {dashboardStats?.retrieval_metrics?.potential_duplicate_pairs ?? 0}</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">Retrieval Activity</div>
                <div className="kpi-value">
                  {dashboardStats?.retrieval_metrics?.total_retrieval_accesses ?? 0}
                  <span className="kpi-sub"> accesses</span>
                </div>
                <div className="kpi-foot">
                  <span>Past 24h: {dashboardStats?.retrieval_metrics?.accessed_last_24h ?? 0}</span>
                  <span>Avg/mem: {dashboardStats?.retrieval_metrics?.avg_accesses_per_memory ?? 0}</span>
                </div>
              </div>
            </div>

            {/* Sub-Navigation Bar */}
            <div className="intelligence-subnav">
              <button
                className={`subnav-btn ${intelligenceSubTab === "graph" ? "active" : ""}`}
                onClick={() => setIntelligenceSubTab("graph")}
              >
                <Network size={14} />
                <span>Relationship Graph</span>
              </button>
              <button
                className={`subnav-btn ${intelligenceSubTab === "consolidation" ? "active" : ""}`}
                onClick={() => {
                  setIntelligenceSubTab("consolidation");
                  if (!consolidationPreview) handlePreviewConsolidation();
                }}
              >
                <Layers size={14} />
                <span>Consolidation Studio</span>
              </button>
              <button
                className={`subnav-btn ${intelligenceSubTab === "retrieval" ? "active" : ""}`}
                onClick={() => setIntelligenceSubTab("retrieval")}
              >
                <Zap size={14} />
                <span>Retrieval 2.0 Simulator</span>
              </button>
              <button
                className={`subnav-btn ${intelligenceSubTab === "lifecycle" ? "active" : ""}`}
                onClick={() => setIntelligenceSubTab("lifecycle")}
              >
                <ShieldCheck size={14} />
                <span>Governance & Audit Trail</span>
              </button>
            </div>

            {/* SUB-VIEW 1: RELATIONSHIP GRAPH */}
            {intelligenceSubTab === "graph" && (
              <div className="graph-view-container">
                <div className="graph-panel-header">
                  <div>
                    <h3>Memory Knowledge Graph</h3>
                    <p>Typed relationships linking memories (uses, prefers, belongs_to, applied_in, supersedes)</p>
                  </div>
                  <div className="graph-header-actions">
                    <button className="action-btn-sm" onClick={fetchGraphData} title="Refresh graph">
                      <RefreshCw size={12} className={loadingGraph ? "spin" : ""} /> Refresh
                    </button>
                    <button className="primary-btn-sm" onClick={() => setShowRelModal(true)}>
                      <Plus size={13} /> Add Relationship
                    </button>
                  </div>
                </div>

                <div className="graph-canvas-wrapper">
                  {graphData.nodes?.length === 0 ? (
                    <div className="empty-graph-state">
                      <Network size={36} />
                      <p>No memories available to visualize yet.</p>
                      <small>Chat with MEMORA AI to generate memories, then connect them into a knowledge graph!</small>
                    </div>
                  ) : (
                    (() => {
                      const width = 760;
                      const height = 440;
                      const cx = width / 2;
                      const cy = height / 2;
                      const count = graphData.nodes.length;
                      const radius = Math.min(width, height) * 0.36;

                      const nodeMap = {};
                      graphData.nodes.forEach((n, idx) => {
                        const angle = (2 * Math.PI * idx) / count;
                        nodeMap[n.id] = {
                          x: cx + radius * Math.cos(angle),
                          y: cy + radius * Math.sin(angle),
                          node: n
                        };
                      });

                      return (
                        <div className="svg-graph-container">
                          <svg viewBox={`0 0 ${width} ${height}`} className="graph-svg">
                            <defs>
                              <marker
                                id="arrowhead"
                                markerWidth="10"
                                markerHeight="7"
                                refX="24"
                                refY="3.5"
                                orient="auto"
                              >
                                <polygon points="0 0, 10 3.5, 0 7" fill="#6366f1" />
                              </marker>
                            </defs>

                            {/* Render Relationship Edges */}
                            {(graphData.edges || []).map((e) => {
                              const s = nodeMap[e.source_id];
                              const t = nodeMap[e.target_id];
                              if (!s || !t) return null;
                              const midX = (s.x + t.x) / 2;
                              const midY = (s.y + t.y) / 2;
                              const isHighlighted =
                                selectedGraphNode?.id === e.source_id || selectedGraphNode?.id === e.target_id;

                              return (
                                <g key={e.id} className={`edge-group ${isHighlighted ? "highlighted" : ""}`}>
                                  <line
                                    x1={s.x}
                                    y1={s.y}
                                    x2={t.x}
                                    y2={t.y}
                                    stroke={isHighlighted ? "#818cf8" : "#2e3c5e"}
                                    strokeWidth={isHighlighted ? 2.5 : 1.5}
                                    strokeDasharray={e.relationship_type === "supersedes" ? "4 3" : "none"}
                                    markerEnd="url(#arrowhead)"
                                  />
                                  <rect
                                    x={midX - 35}
                                    y={midY - 9}
                                    width="70"
                                    height="18"
                                    rx="9"
                                    fill="#0e172a"
                                    stroke="#334155"
                                    strokeWidth="1"
                                  />
                                  <text
                                    x={midX}
                                    y={midY + 3}
                                    textAnchor="middle"
                                    fill="#cbd5e1"
                                    fontSize="9"
                                    fontFamily="sans-serif"
                                    fontWeight="500"
                                  >
                                    {e.relationship_type}
                                  </text>
                                </g>
                              );
                            })}

                            {/* Render Memory Nodes */}
                            {graphData.nodes.map((n) => {
                              const pt = nodeMap[n.id];
                              if (!pt) return null;
                              const isSelected = selectedGraphNode?.id === n.id;
                              const catColors = {
                                preference: "#a855f7",
                                skill: "#10b981",
                                project: "#3b82f6",
                                goal: "#f59e0b",
                                general: "#64748b"
                              };
                              const color = catColors[n.category?.toLowerCase()] || "#6366f1";

                              return (
                                <g
                                  key={n.id}
                                  className={`node-group ${isSelected ? "selected" : ""}`}
                                  onClick={() => setSelectedGraphNode(n)}
                                  style={{ cursor: "pointer" }}
                                >
                                  <circle
                                    cx={pt.x}
                                    cy={pt.y}
                                    r={isSelected ? 20 : 16}
                                    fill={isSelected ? "#1e1b4b" : "#0f172a"}
                                    stroke={color}
                                    strokeWidth={isSelected ? 3 : 2}
                                  />
                                  <circle cx={pt.x} cy={pt.y} r={5} fill={color} />
                                  <text
                                    x={pt.x}
                                    y={pt.y + 28}
                                    textAnchor="middle"
                                    fill="#e2e8f0"
                                    fontSize="11"
                                    fontWeight="600"
                                    className="node-label"
                                  >
                                    {n.memory_key.length > 14 ? n.memory_key.substring(0, 12) + "..." : n.memory_key}
                                  </text>
                                </g>
                              );
                            })}
                          </svg>
                        </div>
                      );
                    })()
                  )}
                </div>

                {/* Node Inspector & Active Edges Panel */}
                <div className="graph-bottom-grid">
                  {selectedGraphNode ? (
                    <div className="node-detail-card">
                      <div className="detail-top">
                        <span className={`cat-badge cat-${selectedGraphNode.category?.toLowerCase()}`}>
                          {selectedGraphNode.category}
                        </span>
                        <h4>#{selectedGraphNode.memory_key}</h4>
                        <button
                          className="explain-btn-inline"
                          onClick={() => handleExplainMemory(selectedGraphNode.id)}
                        >
                          <Eye size={12} /> Explain Decision
                        </button>
                      </div>
                      <p className="detail-content">{selectedGraphNode.content}</p>
                    </div>
                  ) : (
                    <div className="node-detail-placeholder">
                      <Compass size={20} />
                      <p>Click on any memory node in the graph above to inspect its details and connections.</p>
                    </div>
                  )}

                  <div className="edges-list-card">
                    <h4>Connected Edges ({graphData.edges?.length || 0})</h4>
                    <div className="edges-table-scroll">
                      {graphData.edges?.length === 0 ? (
                        <p className="empty-edges-text">No relationship edges defined yet.</p>
                      ) : (
                        graphData.edges.map((e) => (
                          <div className="edge-row" key={e.id}>
                            <span className="edge-source">{e.source_key || e.source_id.substring(0, 8)}</span>
                            <span className="edge-type-pill">{e.relationship_type}</span>
                            <span className="edge-target">{e.target_key || e.target_id.substring(0, 8)}</span>
                            <button
                              onClick={() => handleDeleteRelationship(e.id)}
                              className="delete-edge-btn"
                              title="Delete edge"
                            >
                              <Trash2 size={11} />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* SUB-VIEW 2: CONSOLIDATION STUDIO */}
            {intelligenceSubTab === "consolidation" && (
              <div className="consolidation-studio">
                <div className="studio-header">
                  <div>
                    <h3>Intelligent Memory Consolidation Studio</h3>
                    <p>Detect semantically overlapping memories and merge redundancies with contradiction detection</p>
                  </div>
                  <button
                    className="primary-btn-sm"
                    onClick={handlePreviewConsolidation}
                    disabled={loadingConsolidation}
                  >
                    <RefreshCw size={12} className={loadingConsolidation ? "spin" : ""} /> Scan for Duplicates
                  </button>
                </div>

                {consolidationStatusMsg && (
                  <div className="status-alert-box">
                    <Sparkles size={15} />
                    <span>{consolidationStatusMsg}</span>
                  </div>
                )}

                {loadingConsolidation ? (
                  <div className="studio-loading">
                    <div className="typing">
                      <span></span>
                      <span></span>
                      <span></span>
                      Nemotron is analyzing memory clusters for semantic overlaps and contradictions...
                    </div>
                  </div>
                ) : consolidationPreview?.candidate_groups?.length > 0 ? (
                  <div className="candidate-groups-list">
                    {consolidationPreview.candidate_groups.map((group, idx) => (
                      <div className="consolidation-group-card" key={idx}>
                        <div className="group-card-header">
                          <div className="group-title-box">
                            <span className="cluster-badge">Cluster: {group.cluster_topic}</span>
                            <span className="sim-badge">Similarity: {Math.round(group.avg_similarity * 100)}%</span>
                          </div>
                          {group.is_contradictory && (
                            <div className="contradiction-alert">
                              <AlertTriangle size={13} />
                              <span>Contradictory facts detected — review carefully before merging!</span>
                            </div>
                          )}
                        </div>

                        <div className="source-memories-box">
                          <small className="section-label">Source Memories to Consolidate ({group.source_memories.length}):</small>
                          <div className="source-cards-grid">
                            {group.source_memories.map((sm, sIdx) => (
                              <div className="source-card" key={sIdx}>
                                <div className="source-card-top">
                                  <span className="source-key">#{sm.memory_key}</span>
                                  <span className="cat-pill">{sm.category}</span>
                                </div>
                                <p>{sm.content}</p>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="synthesis-proposal-box">
                          <small className="section-label">Proposed Nemotron Synthesis:</small>
                          <p className="synthesis-text">{group.proposed_consolidated_content}</p>
                          <div className="synthesis-rationale">
                            💡 <strong>Rationale:</strong> {group.consolidation_rationale}
                          </div>
                        </div>

                        <div className="group-actions">
                          <button
                            className="apply-btn"
                            onClick={() => handleApplyConsolidation(group)}
                            disabled={applyingConsolidation}
                          >
                            <Check size={14} />
                            {applyingConsolidation ? "Applying Atomically..." : "Approve & Apply Consolidation"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-studio-state">
                    <CheckCircle2 size={36} />
                    <p>No consolidation proposals at this time.</p>
                    <small>All active memories in this session have distinct semantic identities with no critical overlap.</small>
                  </div>
                )}
              </div>
            )}

            {/* SUB-VIEW 3: RETRIEVAL 2.0 SIMULATOR */}
            {intelligenceSubTab === "retrieval" && (
              <div className="retrieval-simulator">
                <div className="sim-header">
                  <div>
                    <h3>Context-Aware Retrieval 2.0 Simulator</h3>
                    <p>Test multi-factor ranking balancing semantic similarity, keywords, asymptotic recency, and graph boost</p>
                  </div>
                </div>

                <div className="sim-query-bar">
                  <input
                    value={retrievalQuery}
                    onChange={(e) => setRetrievalQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleRunRetrievalTest();
                    }}
                    placeholder="Enter search prompt (e.g. 'What backend stack and tools do I prefer?')..."
                  />
                  <button onClick={handleRunRetrievalTest} disabled={loadingRetrieval || !retrievalQuery.trim()}>
                    <Zap size={14} /> {loadingRetrieval ? "Ranking..." : "Test Retrieval 2.0"}
                  </button>
                </div>

                <div className="retrieval-results-area">
                  {retrievalResults.length === 0 ? (
                    <div className="empty-sim-state">
                      <Zap size={32} />
                      <p>Type a query above to evaluate Context-Aware Retrieval 2.0 scoring in real-time.</p>
                    </div>
                  ) : (
                    <div className="scored-results-list">
                      {retrievalResults.map((r, i) => (
                        <div className="scored-result-card" key={r.id || i}>
                          <div className="result-top">
                            <div className="result-title">
                              <span className="rank-num">#{i + 1}</span>
                              <span className="key-tag">#{r.memory_key}</span>
                              <span className={`cat-badge cat-${r.category?.toLowerCase()}`}>{r.category}</span>
                            </div>
                            <div className="total-score-badge">
                              Total Score: <strong>{(r.similarity_score || 0).toFixed(3)}</strong>
                            </div>
                          </div>

                          <p className="result-content">{r.content}</p>

                          <div className="score-breakdown-row">
                            <span className="breakdown-pill" title="Semantic Cosine Match">
                              Semantic: {r.score_breakdown?.semantic_similarity?.toFixed(2) ?? "—"}
                            </span>
                            <span className="breakdown-pill" title="Exact Keyword Frequency">
                              Keyword: {r.score_breakdown?.keyword_match?.toFixed(2) ?? "—"}
                            </span>
                            <span className="breakdown-pill" title="Calibrated Time-Decay Factor">
                              Recency: {r.score_breakdown?.recency_factor?.toFixed(2) ?? "—"}
                            </span>
                            <span className="breakdown-pill graph" title="Knowledge Graph 1-hop Proximity Boost">
                              Graph: +{r.score_breakdown?.graph_boost?.toFixed(2) ?? "0.00"}
                            </span>
                          </div>

                          {r.retrieval_reason && (
                            <div className="retrieval-reason-box">
                              💡 <small>{r.retrieval_reason}</small>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* SUB-VIEW 4: GOVERNANCE & AUDIT TRAIL */}
            {intelligenceSubTab === "lifecycle" && (
              <div className="lifecycle-view">
                <div className="lifecycle-header">
                  <div>
                    <h3>Memory Lifecycle & Governance Audit Trail</h3>
                    <p>Immutable log of memory state transitions, retention expirations, and user forgetting</p>
                  </div>
                </div>

                <div className="timeline-container">
                  {!dashboardStats?.recent_evolutions || dashboardStats.recent_evolutions.length === 0 ? (
                    <div className="empty-timeline">
                      <ShieldCheck size={32} />
                      <p>No lifecycle events recorded yet for this session.</p>
                    </div>
                  ) : (
                    <div className="timeline-events-list">
                      {dashboardStats.recent_evolutions.map((ev) => (
                        <div className="timeline-item" key={ev.event_id}>
                          <div className={`event-badge badge-${ev.event_type}`}>
                            {ev.event_type}
                          </div>
                          <div className="event-info">
                            <div className="event-title">
                              <strong>#{ev.memory_key}</strong>
                              <span className="event-actor">by {ev.actor}</span>
                              <span className="event-time">
                                {new Date(ev.created_at).toLocaleTimeString([], {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                  second: "2-digit"
                                })}
                              </span>
                            </div>
                            {ev.reason && <p className="event-reason">{ev.reason}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* EXPLAINABILITY MODAL */}
            {showExplainModal && (
              <div className="modal-backdrop" onClick={() => setShowExplainModal(false)}>
                <div className="modal-card" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <div className="modal-title-box">
                      <Eye size={18} className="modal-icon" />
                      <h3>Memory Decision & Lineage Explanation</h3>
                    </div>
                    <button className="close-btn" onClick={() => setShowExplainModal(false)}>
                      <X size={16} />
                    </button>
                  </div>

                  {loadingExplain || !explainData ? (
                    <div className="modal-body-loading">
                      <div className="typing">
                        <span></span>
                        <span></span>
                        <span></span>
                        Loading explanation evidence...
                      </div>
                    </div>
                  ) : (
                    <div className="modal-body">
                      <div className="explain-top-tags">
                        <span className={`cat-badge cat-${explainData.category?.toLowerCase()}`}>
                          {explainData.category}
                        </span>
                        <span className="key-pill">#{explainData.memory_key}</span>
                        <span className={`status-pill status-${explainData.memory_status}`}>
                          Status: {explainData.memory_status}
                        </span>
                      </div>

                      <div className="explain-section">
                        <label>Memory Fact:</label>
                        <p className="explain-content-text">{explainData.content}</p>
                      </div>

                      <div className="explain-section">
                        <label>Extraction Origin:</label>
                        <div className="origin-badge-row">
                          <span className={`origin-pill ${explainData.is_inferred ? "inferred" : "explicit"}`}>
                            {explainData.is_inferred ? "Contextual Inference" : "Explicit Statement"}
                          </span>
                        </div>
                        <p className="explain-desc">{explainData.why_extracted}</p>
                        {explainData.source_message && (
                          <div className="quote-box">
                            <em>"{explainData.source_message}"</em>
                          </div>
                        )}
                      </div>

                      <div className="explain-section">
                        <label>Retention Rationale:</label>
                        <p className="explain-desc">{explainData.why_retained}</p>
                      </div>

                      {explainData.connected_relationships?.length > 0 && (
                        <div className="explain-section">
                          <label>Connected Relationships ({explainData.connected_relationships.length}):</label>
                          <div className="modal-relationships-list">
                            {explainData.connected_relationships.map((cr, idx) => (
                              <div className="modal-rel-item" key={idx}>
                                <span>#{cr.connected_key}</span>
                                <span className="rel-tag">{cr.relationship_type}</span>
                                <small>{cr.content}</small>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {explainData.lifecycle_events?.length > 0 && (
                        <div className="explain-section">
                          <label>Recent Lifecycle Events:</label>
                          <div className="modal-events-list">
                            {explainData.lifecycle_events.map((le, idx) => (
                              <div className="modal-ev-item" key={idx}>
                                <span className="ev-type">{le.event_type}</span>
                                <span className="ev-actor">({le.actor})</span>
                                <span className="ev-reason">{le.reason}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="modal-footer-actions">
                        {explainData.memory_status === "archived" ? (
                          <button
                            className="restore-btn"
                            onClick={() => handleRestoreMemory(explainData.memory_id)}
                          >
                            <RefreshCw size={13} /> Restore from Archive
                          </button>
                        ) : (
                          <button
                            className="archive-btn"
                            onClick={() => handleArchiveMemory(explainData.memory_id)}
                          >
                            <Archive size={13} /> Archive Memory
                          </button>
                        )}
                        <button
                          className="forget-btn danger"
                          onClick={() => handleForgetMemory(explainData.memory_id)}
                          title="Purge vector embedding and deactivate memory"
                        >
                          <Trash2 size={13} /> Forget (Wipe Embedding)
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ADD RELATIONSHIP MODAL */}
            {showRelModal && (
              <div className="modal-backdrop" onClick={() => setShowRelModal(false)}>
                <div className="modal-card sm" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <div className="modal-title-box">
                      <Network size={18} className="modal-icon" />
                      <h3>Create Memory Relationship</h3>
                    </div>
                    <button className="close-btn" onClick={() => setShowRelModal(false)}>
                      <X size={16} />
                    </button>
                  </div>

                  <div className="modal-body form">
                    <div className="form-group">
                      <label>Source Memory:</label>
                      <select value={relSourceId} onChange={(e) => setRelSourceId(e.target.value)}>
                        <option value="">Select source memory...</option>
                        {memories.map((m) => (
                          <option key={m.id} value={m.id}>
                            #{m.memory_key} - {m.content.substring(0, 45)}...
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Relationship Type:</label>
                      <select value={relType} onChange={(e) => setRelType(e.target.value)}>
                        <option value="uses">uses</option>
                        <option value="prefers">prefers</option>
                        <option value="belongs_to">belongs_to</option>
                        <option value="applied_in">applied_in</option>
                        <option value="supersedes">supersedes</option>
                        <option value="relates_to">relates_to</option>
                        <option value="depends_on">depends_on</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Target Memory:</label>
                      <select value={relTargetId} onChange={(e) => setRelTargetId(e.target.value)}>
                        <option value="">Select target memory...</option>
                        {memories.map((m) => (
                          <option key={m.id} value={m.id} disabled={m.id === relSourceId}>
                            #{m.memory_key} - {m.content.substring(0, 45)}...
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Strength: {relStrength}</label>
                      <input
                        type="range"
                        min="0.1"
                        max="1.0"
                        step="0.05"
                        value={relStrength}
                        onChange={(e) => setRelStrength(parseFloat(e.target.value))}
                      />
                    </div>

                    <div className="modal-footer-actions">
                      <button className="secondary-btn" onClick={() => setShowRelModal(false)}>
                        Cancel
                      </button>
                      <button
                        className="primary-btn-sm"
                        onClick={handleCreateRelationship}
                        disabled={!relSourceId || !relTargetId || relSourceId === relTargetId}
                      >
                        Create Relationship Edge
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
