import React from "react";
import {
  BrainCircuit,
  Database,
  Layers,
  Network,
  Bot,
  Clock,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  ArrowRight,
  Server,
} from "lucide-react";
import { Skeleton } from "../common/EmptyState";

export function OverviewView({
  dashboardStats,
  loadingDashboard,
  tasks,
  loadingTasks,
  systemInfo,
  onNavigate,
}) {
  const pendingTasks = (tasks || []).filter((t) => t.status === "awaiting_approval");
  const completedTasks = (tasks || []).filter((t) => t.status === "completed" || t.status === "succeeded");
  const failedTasks = (tasks || []).filter((t) => t.status === "failed" || t.status === "needs_reconciliation");

  return (
    <div className="view-container overview-view" style={{ padding: "24px", maxWidth: "1380px", margin: "0 auto" }}>
      {/* Pending Approvals Urgent Banner */}
      {pendingTasks.length > 0 && (
        <div
          className="pending-approvals-alert"
          style={{
            background: "rgba(245, 158, 11, 0.12)",
            border: "1px solid var(--color-warning-border, rgba(245, 158, 11, 0.4))",
            borderRadius: "var(--radius-lg, 14px)",
            padding: "16px 20px",
            marginBottom: "24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "rgba(245, 158, 11, 0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-warning, #f59e0b)",
              }}
            >
              <ShieldAlert size={20} />
            </div>
            <div>
              <h4 style={{ margin: "0 0 2px 0", fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                {pendingTasks.length} Agent Action{pendingTasks.length > 1 ? "s" : ""} Awaiting Your Approval
              </h4>
              <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                Potentially impactful operations (e.g. note creation, external API side effects) are paused pending your signature.
              </p>
            </div>
          </div>
          <button
            className="btn btn-warning btn-sm"
            style={{
              background: "var(--color-warning, #f59e0b)",
              color: "#000000",
              fontWeight: 600,
              flexShrink: 0,
            }}
            onClick={() => onNavigate("agent")}
          >
            Review Approvals
          </button>
        </div>
      )}

      {/* Primary Metrics Grid */}
      <div
        className="metrics-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        {/* Active Memories */}
        <div className="card card-hover" onClick={() => onNavigate("memories")} style={{ cursor: "pointer" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Active Memories
            </span>
            <div style={{ padding: "6px", borderRadius: "8px", background: "rgba(99, 102, 241, 0.12)", color: "#818cf8" }}>
              <BrainCircuit size={18} />
            </div>
          </div>
          {loadingDashboard ? (
            <Skeleton height="36px" width="80px" />
          ) : (
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                {dashboardStats?.active_memories ?? 0}
              </span>
              <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                / {dashboardStats?.total_memories ?? 0} total
              </span>
            </div>
          )}
          <div style={{ marginTop: "12px", display: "flex", gap: "8px", fontSize: "0.75rem", color: "var(--text-muted)" }}>
            <span>{dashboardStats?.persistent_count ?? 0} persistent</span>
            <span>•</span>
            <span>{dashboardStats?.temporary_count ?? 0} temporary</span>
          </div>
        </div>

        {/* Knowledge Graph Edges */}
        <div className="card card-hover" onClick={() => onNavigate("graph")} style={{ cursor: "pointer" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Relationship Graph
            </span>
            <div style={{ padding: "6px", borderRadius: "8px", background: "rgba(6, 182, 212, 0.12)", color: "#38bdf8" }}>
              <Network size={18} />
            </div>
          </div>
          {loadingDashboard ? (
            <Skeleton height="36px" width="80px" />
          ) : (
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                {dashboardStats?.relationship_count ?? 0}
              </span>
              <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>directed edges</span>
            </div>
          )}
          <div style={{ marginTop: "12px", fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Multi-hop associative retrieval active
          </div>
        </div>

        {/* Consolidations */}
        <div className="card card-hover" onClick={() => onNavigate("consolidation")} style={{ cursor: "pointer" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Consolidations
            </span>
            <div style={{ padding: "6px", borderRadius: "8px", background: "rgba(16, 185, 129, 0.12)", color: "#34d399" }}>
              <Layers size={18} />
            </div>
          </div>
          {loadingDashboard ? (
            <Skeleton height="36px" width="80px" />
          ) : (
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                {dashboardStats?.consolidation_count ?? 0}
              </span>
              <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>clusters merged</span>
            </div>
          )}
          <div style={{ marginTop: "12px", fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Contradiction & duplicate deduplication
          </div>
        </div>

        {/* Agent Tasks */}
        <div className="card card-hover" onClick={() => onNavigate("tasks")} style={{ cursor: "pointer" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Agent Executions
            </span>
            <div style={{ padding: "6px", borderRadius: "8px", background: "rgba(245, 158, 11, 0.12)", color: "#fbbf24" }}>
              <Bot size={18} />
            </div>
          </div>
          {loadingTasks ? (
            <Skeleton height="36px" width="80px" />
          ) : (
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                {(tasks || []).length}
              </span>
              <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>tasks tracked</span>
            </div>
          )}
          <div style={{ marginTop: "12px", display: "flex", gap: "8px", fontSize: "0.75rem", color: "var(--text-muted)" }}>
            <span style={{ color: "var(--color-success)" }}>{completedTasks.length} passed</span>
            <span>•</span>
            <span style={{ color: failedTasks.length > 0 ? "var(--color-danger)" : "inherit" }}>
              {failedTasks.length} failed
            </span>
          </div>
        </div>
      </div>

      {/* Middle Row: Categories & System Health */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
          gap: "20px",
          marginBottom: "24px",
        }}
      >
        {/* Category Distribution Card */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Database size={18} color="var(--accent-primary)" />
              <span>Memory Categories</span>
            </h3>
            <button className="btn btn-ghost btn-sm" onClick={() => onNavigate("memories")}>
              View All <ArrowRight size={13} />
            </button>
          </div>
          {loadingDashboard ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <Skeleton height="24px" />
              <Skeleton height="24px" />
              <Skeleton height="24px" />
            </div>
          ) : dashboardStats?.category_counts && Object.keys(dashboardStats.category_counts).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {Object.entries(dashboardStats.category_counts).map(([cat, count]) => {
                const total = dashboardStats.total_memories || 1;
                const pct = Math.round((count / total) * 100);
                return (
                  <div key={cat}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: "4px" }}>
                      <span style={{ textTransform: "capitalize", color: "var(--text-primary)", fontWeight: 500 }}>
                        {cat.replace("_", " ")}
                      </span>
                      <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-family-mono)" }}>
                        {count} ({pct}%)
                      </span>
                    </div>
                    <div style={{ height: "6px", borderRadius: "3px", background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${pct}%`,
                          borderRadius: "3px",
                          background: "var(--accent-primary, #6366f1)",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
              No memories recorded yet. Start chatting to extract memories automatically.
            </div>
          )}
        </div>

        {/* Live Infrastructure & Health Card */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              <Server size={18} color="var(--color-success)" />
              <span>Infrastructure & Live Telemetry</span>
            </h3>
            <span className="badge badge-emerald">Operational</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", fontSize: "0.84rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-muted)" }}>Database Provider:</span>
              <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                {systemInfo?.database_provider || "Neon Lakebase Postgres (pgvector)"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-muted)" }}>Database Pool:</span>
              <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-family-mono)" }}>
                {systemInfo?.database_pool_size ?? 1} total / {systemInfo?.database_free_connections ?? 0} idle
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-muted)" }}>LLM Engine:</span>
              <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                {systemInfo?.llm_model || "NVIDIA Nemotron-3_5-Lightning"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span style={{ color: "var(--text-muted)" }}>Embedding Model:</span>
              <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                {systemInfo?.embedding_model || "Qwen/Qwen3-Embedding-8B"} ({systemInfo?.embedding_dim || 4096}-d)
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0" }}>
              <span style={{ color: "var(--text-muted)" }}>Worker Lease Node:</span>
              <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-family-mono)", fontSize: "0.78rem" }}>
                {systemInfo?.worker_id ? systemInfo.worker_id.slice(0, 24) + "..." : "local-worker"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Section: Recent Tasks & Quick Actions */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            <Clock size={18} color="var(--accent-primary)" />
            <span>Recent Agent Tasks</span>
          </h3>
          <button className="btn btn-ghost btn-sm" onClick={() => onNavigate("tasks")}>
            View Task History <ArrowRight size={13} />
          </button>
        </div>
        {loadingTasks ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <Skeleton height="40px" />
            <Skeleton height="40px" />
          </div>
        ) : tasks && tasks.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {tasks.slice(0, 4).map((task) => (
              <div
                key={task.id}
                onClick={() => onNavigate("agent")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-subtle)",
                  cursor: "pointer",
                  transition: "all var(--transition-fast)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
                  {task.status === "completed" || task.status === "succeeded" ? (
                    <CheckCircle2 size={16} color="var(--color-success)" style={{ flexShrink: 0 }} />
                  ) : task.status === "awaiting_approval" ? (
                    <AlertTriangle size={16} color="var(--color-warning)" style={{ flexShrink: 0 }} />
                  ) : task.status === "failed" || task.status === "needs_reconciliation" ? (
                    <XCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
                  ) : (
                    <Activity size={16} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
                  )}
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <div style={{ fontSize: "0.86rem", fontWeight: 500, color: "var(--text-primary)" }}>
                      {task.instruction}
                    </div>
                    <div style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                      ID: {task.id.slice(0, 8)} • Steps: {task.plan?.steps?.length || 0}
                    </div>
                  </div>
                </div>
                <span
                  className={`badge ${
                    task.status === "completed" || task.status === "succeeded"
                      ? "badge-emerald"
                      : task.status === "awaiting_approval"
                      ? "badge-amber"
                      : task.status === "failed" || task.status === "needs_reconciliation"
                      ? "badge-rose"
                      : "badge-indigo"
                  }`}
                  style={{ flexShrink: 0 }}
                >
                  {task.status.replace("_", " ")}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
            No agent tasks executed in this session yet. Submit a task in the Agent Workspace to see it here.
          </div>
        )}
      </div>
    </div>
  );
}
