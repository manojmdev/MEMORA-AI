import React, { useState, useEffect, useCallback } from "react";
import "./styles/theme.css";
import "./styles/components.css";
import "./App.css";

import { api, getStoredSessionId, setStoredSessionId } from "./api/client";
import { ToastProvider, useToast } from "./components/layout/Toast";
import { Sidebar } from "./components/layout/Sidebar";
import { TopNav } from "./components/layout/TopNav";

import { OverviewView } from "./components/overview/OverviewView";
import { ChatView } from "./components/chat/ChatView";
import { MemoryExplorerView } from "./components/memories/MemoryExplorerView";
import { MemoryGraphView } from "./components/graph/MemoryGraphView";
import { ConsolidationStudioView } from "./components/consolidation/ConsolidationStudioView";
import { AgentWorkspaceView } from "./components/agent/AgentWorkspaceView";
import { TaskHistoryView } from "./components/tasks/TaskHistoryView";
import { SettingsView } from "./components/settings/SettingsView";

function AppContent() {
  const { showToast } = useToast();

  // Navigation & Shell State
  const [activeNav, setActiveNav] = useState("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("memora_theme") || "dark");
  const [refreshing, setRefreshing] = useState(false);

  // Session & Auth
  const [sessionId, setSessionId] = useState(() => getStoredSessionId());

  // Backend Telemetry
  const [backendHealthy, setBackendHealthy] = useState(true);
  const [dbConnected, setDbConnected] = useState(true);
  const [dbPoolInfo, setDbPoolInfo] = useState("1/0");
  const [systemInfo, setSystemInfo] = useState(null);

  // Business Data
  const [dashboardStats, setDashboardStats] = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);

  const [memories, setMemories] = useState([]);
  const [loadingMemories, setLoadingMemories] = useState(false);

  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loadingGraph, setLoadingGraph] = useState(false);

  const [consolidationPreview, setConsolidationPreview] = useState(null);
  const [loadingConsolidation, setLoadingConsolidation] = useState(false);

  const [tasks, setTasks] = useState([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [activeTask, setActiveTask] = useState(null);
  const [agentRunning, setAgentRunning] = useState(false);
  const [taskCheckpoints, setTaskCheckpoints] = useState([]);

  // Chat State
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I am MEMORA AI, connected to NVIDIA Nemotron and Neon Lakebase Postgres. Share your preferences, skills, or projects, and I will remember and adapt to them across sessions.",
    },
  ]);
  const [chatLoading, setChatLoading] = useState(false);

  // Apply Theme Token Attribute
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("memora_theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  // Health & System Info Poller
  const fetchHealthAndSystem = useCallback(async () => {
    try {
      const health = await api.checkHealth();
      setBackendHealthy(health.status === "healthy");
      setDbConnected(health.database?.connected ?? false);

      const sys = await api.getSystemInfo();
      setSystemInfo(sys);
      if (sys.database_pool_size !== undefined) {
        setDbPoolInfo(`${sys.database_pool_size}/${sys.database_free_connections}`);
      }
    } catch {
      setBackendHealthy(false);
      setDbConnected(false);
    }
  }, []);

  // Fetch Dashboard Stats
  const fetchDashboardStats = useCallback(async () => {
    setLoadingDashboard(true);
    try {
      const stats = await api.getDashboard(sessionId);
      setDashboardStats(stats);
    } catch {
      // Graceful fallback
    } finally {
      setLoadingDashboard(false);
    }
  }, [sessionId]);

  // Fetch Memories
  const fetchMemories = useCallback(async () => {
    setLoadingMemories(true);
    try {
      const res = await api.listMemories(sessionId, null, null);
      setMemories(res?.memories || []);
    } catch (e) {
      console.error("Failed to fetch memories:", e);
    } finally {
      setLoadingMemories(false);
    }
  }, [sessionId]);

  // Fetch Graph
  const fetchGraphData = useCallback(async () => {
    setLoadingGraph(true);
    try {
      const data = await api.getMemoryGraph(sessionId);
      setGraphData(data || { nodes: [], edges: [] });
    } catch (e) {
      console.error("Failed to fetch graph:", e);
    } finally {
      setLoadingGraph(false);
    }
  }, [sessionId]);

  // Fetch Tasks
  const fetchTasks = useCallback(async () => {
    setLoadingTasks(true);
    try {
      const list = await api.listTasks(sessionId, 50);
      setTasks(list || []);
      // If there's an active running or awaiting task, keep activeTask synced
      if (list && list.length > 0) {
        const found = list.find((t) => t.status === "running" || t.status === "awaiting_approval");
        if (found) {
          setActiveTask(found);
        }
      }
    } catch (e) {
      console.error("Failed to fetch tasks:", e);
    } finally {
      setLoadingTasks(false);
    }
  }, [sessionId]);

  // Initial Load & Session Changes
  useEffect(() => {
    fetchHealthAndSystem();
    fetchDashboardStats();
    fetchMemories();
    fetchGraphData();
    fetchTasks();
  }, [sessionId, fetchHealthAndSystem, fetchDashboardStats, fetchMemories, fetchGraphData, fetchTasks]);

  // Global Refresh Handler
  const handleGlobalRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchHealthAndSystem(),
        fetchDashboardStats(),
        fetchMemories(),
        fetchGraphData(),
        fetchTasks(),
      ]);
      showToast("Workspace data synchronized", "success", 2000);
    } catch {
      showToast("Data refresh encountered issues", "error");
    } finally {
      setRefreshing(false);
    }
  };

  // Chat Handler
  const handleSendMessage = async (text) => {
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setChatLoading(true);

    try {
      const res = await api.chat(text, sessionId);
      const assistantMsg = {
        role: "assistant",
        content: res.reply,
        memories_recalled: res.memories_recalled || [],
        memories_extracted: res.memories_extracted || [],
        memory_persistence_status: res.memory_persistence_status || "success",
        memory_persistence_error: res.memory_persistence_error || null,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      if (res.memory_persistence_status === "failed") {
        showToast(
          `Memory persistence notice: ${res.memory_persistence_error || "Could not save memories."}`,
          "warning",
          5000
        );
      } else if (res.memory_persistence_status === "partial") {
        showToast(
          "Memory persistence notice: Some memories could not be saved.",
          "warning",
          4000
        );
      }

      // Refresh memories and dashboard stats to reflect newly extracted items
      fetchMemories();
      fetchDashboardStats();
      fetchGraphData();
    } catch (e) {
      showToast(e.message || "Failed to generate reply", "error");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ Error: ${e.message || "Unable to complete chat request."}`,
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Memory Actions
  const handlePatchMemory = async (memoryId, updates) => {
    await api.patchMemory(sessionId, memoryId, updates);
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  const handleArchiveMemory = async (memoryId) => {
    await api.archiveMemory(sessionId, memoryId);
    showToast("Memory archived", "success");
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  const handleRestoreMemory = async (memoryId) => {
    await api.restoreMemory(sessionId, memoryId);
    showToast("Memory restored to active retrieval", "success");
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  const handleForgetMemory = async (memoryId) => {
    await api.forgetMemory(sessionId, memoryId);
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  const handleDeleteMemory = async (memoryId) => {
    await api.deleteMemory(sessionId, memoryId);
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  const handleExplainMemory = async (memoryId) => {
    return api.explainMemory(sessionId, memoryId);
  };

  const handleClearSessionMemories = async () => {
    await api.clearMemories(sessionId);
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  // Relationship Graph Actions
  const handleCreateRelationship = async (data) => {
    await api.createRelationship(sessionId, data);
    await Promise.all([fetchGraphData(), fetchDashboardStats()]);
  };

  const handleDeleteRelationship = async (relationshipId) => {
    await api.deleteRelationship(sessionId, relationshipId);
    await Promise.all([fetchGraphData(), fetchDashboardStats()]);
  };

  // Consolidation Studio Actions
  const handleGenerateConsolidationPreview = async (minSim, maxCluster) => {
    setLoadingConsolidation(true);
    try {
      const preview = await api.previewConsolidation(sessionId, minSim, maxCluster);
      setConsolidationPreview(preview);
    } finally {
      setLoadingConsolidation(false);
    }
  };

  const handleApplyConsolidation = async (data) => {
    await api.applyConsolidation(sessionId, data);
    await Promise.all([fetchMemories(), fetchDashboardStats(), fetchGraphData()]);
  };

  // Agent Actions
  const handleSubmitAgentTask = async (instruction, requireApproval, maxSteps) => {
    setAgentRunning(true);
    try {
      const task = await api.runAgent(sessionId, instruction, requireApproval, maxSteps);
      setActiveTask(task);
      showToast(`Agent plan generated (${task.plan?.steps?.length || 0} steps)`, "success");
      await fetchTasks();
    } catch (e) {
      showToast(e.message || "Failed to execute agent task", "error");
    } finally {
      setAgentRunning(false);
    }
  };

  const handleApproveTask = async (taskId, token, feedback) => {
    const updated = await api.approveTask(sessionId, taskId, token, feedback);
    setActiveTask(updated);
    await fetchTasks();
  };

  const handleRejectTask = async (taskId, token, reason) => {
    const updated = await api.rejectTask(sessionId, taskId, token, reason);
    setActiveTask(updated);
    await fetchTasks();
  };

  const handleCancelTask = async (taskId, reason) => {
    const updated = await api.cancelTask(sessionId, taskId, reason);
    setActiveTask(updated);
    await fetchTasks();
  };

  const handleRetryTask = async (taskId, fromCheckpointId) => {
    const updated = await api.retryTask(sessionId, taskId, fromCheckpointId);
    setActiveTask(updated);
    await fetchTasks();
  };

  const handleFetchCheckpoints = async (taskId) => {
    try {
      const res = await api.getTaskCheckpoints(sessionId, taskId);
      setTaskCheckpoints(res?.checkpoints || []);
    } catch {
      showToast("Unable to load checkpoints", "error");
    }
  };

  // View Titles & Subtitles
  const getNavMeta = () => {
    switch (activeNav) {
      case "overview":
        return { title: "Overview Dashboard", subtitle: "Live metrics, memory health & autonomous telemetry" };
      case "chat":
        return { title: "AI Memory Chat", subtitle: "Nemotron conversational interface with hybrid memory context" };
      case "memories":
        return { title: "Memory Explorer", subtitle: "Search, filter, inspect provenance, and manage memory lifecycle" };
      case "graph":
        return { title: "Memory Relationship Graph", subtitle: "Interactive directed knowledge graph with multi-hop connections" };
      case "consolidation":
        return { title: "Consolidation Studio", subtitle: "Semantic clustering, contradiction resolution, and lineage synthesis" };
      case "agent":
        return { title: "Agent Workspace", subtitle: "Multi-step DAG planning, checkpointing, and execution engine" };
      case "tasks":
        return { title: "Task History & Audit", subtitle: "Historical executions, step timelines, and verification logs" };
      case "settings":
        return { title: "Settings & Privacy", subtitle: "Session isolation, HMAC authentication tokens, and infrastructure" };
      default:
        return { title: "MEMORA AI", subtitle: "" };
    }
  };

  const navMeta = getNavMeta();
  const pendingApprovalsCount = tasks.filter((t) => t.status === "awaiting_approval").length;

  return (
    <div className="app-shell" style={{ display: "flex", minHeight: "100vh", background: "var(--bg-app)" }}>
      {/* Navigation Sidebar */}
      <Sidebar
        activeNav={activeNav}
        onSelectNav={setActiveNav}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        pendingApprovalsCount={pendingApprovalsCount}
        totalMemoriesCount={memories.length}
        sessionId={sessionId}
      />

      {/* Main Content Workspace */}
      <div
        className="app-main-workspace"
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          background: "var(--bg-app)",
        }}
      >
        <TopNav
          title={navMeta.title}
          subtitle={navMeta.subtitle}
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
          backendHealthy={backendHealthy}
          dbConnected={dbConnected}
          dbPoolInfo={dbPoolInfo}
          sessionId={sessionId}
          theme={theme}
          onToggleTheme={toggleTheme}
          onNewTask={() => setActiveNav("agent")}
          onRefreshData={handleGlobalRefresh}
          refreshing={refreshing}
        />

        {/* View Router */}
        <main style={{ flex: 1, overflowY: "auto" }}>
          {activeNav === "overview" && (
            <OverviewView
              dashboardStats={dashboardStats}
              loadingDashboard={loadingDashboard}
              tasks={tasks}
              loadingTasks={loadingTasks}
              systemInfo={systemInfo}
              onNavigate={setActiveNav}
            />
          )}

          {activeNav === "chat" && (
            <ChatView
              messages={messages}
              onSendMessage={handleSendMessage}
              loading={chatLoading}
              onClearChat={() =>
                setMessages([
                  {
                    role: "assistant",
                    content: "Conversation history cleared. Share preferences, skills, or goals to begin.",
                  },
                ])
              }
              sessionId={sessionId}
            />
          )}

          {activeNav === "memories" && (
            <MemoryExplorerView
              memories={memories}
              loading={loadingMemories}
              onRefresh={fetchMemories}
              onPatchMemory={handlePatchMemory}
              onArchiveMemory={handleArchiveMemory}
              onRestoreMemory={handleRestoreMemory}
              onForgetMemory={handleForgetMemory}
              onDeleteMemory={handleDeleteMemory}
              onExplainMemory={handleExplainMemory}
            />
          )}

          {activeNav === "graph" && (
            <MemoryGraphView
              graphData={graphData}
              loading={loadingGraph}
              onRefresh={fetchGraphData}
              onCreateRelationship={handleCreateRelationship}
              onDeleteRelationship={handleDeleteRelationship}
              memories={memories}
              sessionId={sessionId}
            />
          )}

          {activeNav === "consolidation" && (
            <ConsolidationStudioView
              previewData={consolidationPreview}
              loadingPreview={loadingConsolidation}
              onGeneratePreview={handleGenerateConsolidationPreview}
              onApplyConsolidation={handleApplyConsolidation}
              sessionId={sessionId}
            />
          )}

          {activeNav === "agent" && (
            <AgentWorkspaceView
              activeTask={activeTask}
              running={agentRunning}
              onSubmitTask={handleSubmitAgentTask}
              onApproveTask={handleApproveTask}
              onRejectTask={handleRejectTask}
              onCancelTask={handleCancelTask}
              onRetryTask={handleRetryTask}
              checkpoints={taskCheckpoints}
              onFetchCheckpoints={handleFetchCheckpoints}
              sessionId={sessionId}
            />
          )}

          {activeNav === "tasks" && (
            <TaskHistoryView
              tasks={tasks}
              loading={loadingTasks}
              onRefresh={fetchTasks}
              onSelectTask={(task) => {
                setActiveTask(task);
                setActiveNav("agent");
              }}
              onRetryTask={handleRetryTask}
            />
          )}

          {activeNav === "settings" && (
            <SettingsView
              sessionId={sessionId}
              onUpdateSessionId={(newId) => {
                setSessionId(newId);
                setStoredSessionId(newId);
              }}
              onClearSessionMemories={handleClearSessionMemories}
              memories={memories}
              systemInfo={systemInfo}
              theme={theme}
              onToggleTheme={toggleTheme}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}
