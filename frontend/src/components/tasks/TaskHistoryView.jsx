import React, { useState, useMemo } from "react";
import {
  Clock,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  ArrowRight,
  Eye,
  RefreshCw,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { EmptyState, Skeleton } from "../common/EmptyState";

export function TaskHistoryView({
  tasks,
  loading,
  onRefresh,
  onSelectTask,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [inspectingTask, setInspectingTask] = useState(null);

  const filteredTasks = useMemo(() => {
    return (tasks || []).filter((t) => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchInst = t.instruction?.toLowerCase().includes(q);
        const matchId = t.id?.toLowerCase().includes(q);
        if (!matchInst && !matchId) return false;
      }
      return true;
    });
  }, [tasks, statusFilter, searchQuery]);

  return (
    <div
      className="view-container task-history-view"
      style={{
        padding: "24px",
        maxWidth: "1380px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      {/* Controls Bar */}
      <div
        className="card"
        style={{
          padding: "14px 18px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: "1 1 300px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "var(--bg-input)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "0 12px",
              width: "100%",
            }}
          >
            <Search size={15} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Filter tasks by instruction or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                border: "none",
                background: "transparent",
                color: "var(--text-primary)",
                padding: "8px 0",
                outline: "none",
                width: "100%",
                fontSize: "0.86rem",
              }}
            />
          </div>

          <select
            className="select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ width: "auto", minWidth: "160px" }}
          >
            <option value="all">All Statuses ({tasks?.length || 0})</option>
            <option value="completed">Completed</option>
            <option value="awaiting_approval">Awaiting Approval</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
            <option value="running">Running</option>
            <option value="needs_reconciliation">Needs Reconciliation</option>
          </select>
        </div>

        {onRefresh && (
          <button className="btn btn-ghost btn-sm" onClick={onRefresh} title="Refresh Task Records">
            <RefreshCw size={15} className={loading ? "spinning" : ""} />
          </button>
        )}
      </div>

      {/* Task List Table / Cards */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <Skeleton height="70px" borderRadius="10px" />
          <Skeleton height="70px" borderRadius="10px" />
          <Skeleton height="70px" borderRadius="10px" />
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Clock}
            title="No Tasks Recorded"
            description={
              searchQuery || statusFilter !== "all"
                ? "No tasks matched your search or status criteria."
                : "No agent tasks have been executed in this session yet."
            }
          />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {filteredTasks.map((t) => {
            const isCompleted = t.status === "completed";
            const isPending = t.status === "awaiting_approval";
            const isFailed = t.status === "failed";

            return (
              <div
                key={t.id}
                className="card card-hover"
                style={{
                  padding: "14px 18px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "14px",
                  borderLeft: `4px solid ${
                    isCompleted
                      ? "var(--color-success)"
                      : isPending
                      ? "var(--color-warning)"
                      : isFailed
                      ? "var(--color-danger)"
                      : "var(--accent-primary)"
                  }`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "14px", minWidth: 0, flex: 1 }}>
                  <div>
                    {isCompleted ? (
                      <CheckCircle2 size={20} color="var(--color-success)" />
                    ) : isPending ? (
                      <AlertTriangle size={20} color="var(--color-warning)" />
                    ) : isFailed ? (
                      <XCircle size={20} color="var(--color-danger)" />
                    ) : (
                      <Activity size={20} color="var(--accent-primary)" />
                    )}
                  </div>

                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div
                      style={{
                        fontSize: "0.92rem",
                        fontWeight: 600,
                        color: "var(--text-primary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        marginBottom: "3px",
                      }}
                    >
                      {t.instruction}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", gap: "10px" }}>
                      <span>ID: <code>{t.id.slice(0, 10)}...</code></span>
                      <span>•</span>
                      <span>Steps: {t.plan?.steps?.length || 0}</span>
                      <span>•</span>
                      <span>Created: {new Date(t.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
                  <span
                    className={`badge ${
                      isCompleted
                        ? "badge-emerald"
                        : isPending
                        ? "badge-amber"
                        : isFailed
                        ? "badge-rose"
                        : "badge-indigo"
                    }`}
                  >
                    {t.status.replace("_", " ")}
                  </span>

                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setInspectingTask(t)}
                    title="Inspect task execution details"
                  >
                    <Eye size={14} />
                    <span>Details</span>
                  </button>

                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => onSelectTask(t)}
                    title="Load into active Agent Workspace"
                  >
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Task Details Modal */}
      {inspectingTask && (
        <Modal
          isOpen={!!inspectingTask}
          onClose={() => setInspectingTask(null)}
          title={`Task Execution Log: ${inspectingTask.id.slice(0, 10)}...`}
          maxWidth="720px"
          footer={
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  onSelectTask(inspectingTask);
                  setInspectingTask(null);
                }}
              >
                Open in Workspace
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => setInspectingTask(null)}>
                Close
              </button>
            </div>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "0.85rem" }}>
            <div style={{ background: "var(--bg-surface-elevated)", padding: "12px", borderRadius: "8px" }}>
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "4px" }}>
                Goal Instruction
              </div>
              <div style={{ color: "var(--text-primary)", fontWeight: 600 }}>{inspectingTask.instruction}</div>
            </div>

            {/* Plan Steps */}
            <div>
              <h5 style={{ margin: "0 0 8px 0", color: "var(--text-primary)", fontSize: "0.85rem" }}>
                Plan Steps & DAG Execution Status
              </h5>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {(inspectingTask.plan?.steps || []).map((st, sIdx) => (
                  <div
                    key={st.step_id || sIdx}
                    style={{
                      background: "var(--bg-input)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "6px",
                      padding: "8px 12px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                        {sIdx + 1}. {st.tool_name}
                      </span>
                      <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{st.description}</div>
                    </div>
                    <span
                      className={`badge ${
                        st.status === "completed"
                          ? "badge-emerald"
                          : st.status === "failed"
                          ? "badge-rose"
                          : "badge-neutral"
                      }`}
                    >
                      {st.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Response Output */}
            {inspectingTask.response && (
              <div>
                <h5 style={{ margin: "0 0 6px 0", color: "var(--color-success)", fontSize: "0.85rem" }}>
                  Assistant Response
                </h5>
                <div
                  style={{
                    background: "rgba(16, 185, 129, 0.06)",
                    border: "1px solid var(--color-success-border)",
                    borderRadius: "8px",
                    padding: "12px",
                    color: "var(--text-primary)",
                    lineHeight: 1.5,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {inspectingTask.response}
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
