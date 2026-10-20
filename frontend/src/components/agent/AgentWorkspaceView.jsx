import React, { useState } from "react";
import {
  Bot,
  Play,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ShieldAlert,
  RotateCcw,
  StopCircle,
  Sparkles,
  Check,
  X,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { EmptyState } from "../common/EmptyState";
import { useToast } from "../layout/Toast";

export function AgentWorkspaceView({
  activeTask,
  running,
  onSubmitTask,
  onApproveTask,
  onRejectTask,
  onCancelTask,
  onRetryTask,
  checkpoints,
  onFetchCheckpoints,
  sessionId: _sessionId,
}) {
  const { showToast } = useToast();
  const [instruction, setInstruction] = useState("");
  const [requireApproval, setRequireApproval] = useState(false);
  const [maxSteps, setMaxSteps] = useState(10);
  const [showCheckpointsModal, setShowCheckpointsModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!instruction.trim() || running) return;
    onSubmitTask(instruction.trim(), requireApproval, maxSteps);
  };

  const handleApprove = async () => {
    if (!activeTask) return;
    const approvalToken = activeTask.plan?.approval_token;
    if (!approvalToken) {
      showToast("No cryptographic approval token present on this task", "error");
      return;
    }
    setActionLoading(true);
    try {
      await onApproveTask(activeTask.id, approvalToken, "Approved via Agent Workspace UI");
      showToast("Task approval dispatched successfully", "success");
    } catch (e) {
      showToast(e.message || "Approval failed", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!activeTask) return;
    const approvalToken = activeTask.plan?.approval_token;
    if (!approvalToken) return;
    setActionLoading(true);
    try {
      await onRejectTask(activeTask.id, approvalToken, rejectReason || "Rejected by user");
      showToast("Task rejected and halted", "warning");
      setShowRejectModal(false);
      setRejectReason("");
    } catch (e) {
      showToast(e.message || "Rejection failed", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!activeTask) return;
    setActionLoading(true);
    try {
      await onCancelTask(activeTask.id, "Cancelled by user");
      showToast("Cancellation signal sent", "warning");
    } catch (e) {
      showToast(e.message || "Cancellation failed", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetry = async () => {
    if (!activeTask) return;
    setActionLoading(true);
    try {
      await onRetryTask(activeTask.id);
      showToast("Retrying task from latest checkpoint", "success");
    } catch (e) {
      showToast(e.message || "Retry failed", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenCheckpoints = async () => {
    if (activeTask) {
      await onFetchCheckpoints(activeTask.id);
      setShowCheckpointsModal(true);
    }
  };

  const plan = activeTask?.plan;
  const steps = plan?.steps || [];
  const status = activeTask?.status;
  const isAwaitingApproval = status === "awaiting_approval";
  const isNeedsReconciliation = status === "needs_reconciliation";

  return (
    <div
      className="view-container agent-workspace-view"
      style={{
        padding: "24px",
        maxWidth: "1380px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "20px",
      }}
    >
      {/* Task Submission Card */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, #6366f1 0%, #4338ca 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ffffff",
            }}
          >
            <Bot size={20} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Autonomous Agent Orchestration Studio
            </h3>
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              Submit complex goals. The agent decomposes goals into DAG steps, checks permissions, checkpoints progress, and seeks approval for side effects.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <textarea
            className="textarea"
            rows={3}
            placeholder="E.g., 'Research my Python preferences and create a study guide note on building async FastAPI microservices with pgvector'"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={running}
          />

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.82rem", color: "var(--text-secondary)", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={requireApproval}
                  onChange={(e) => setRequireApproval(e.target.checked)}
                  disabled={running}
                />
                <span>Enforce approval for sensitive operations</span>
              </label>

              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Max Steps:</span>
                <input
                  type="number"
                  min="2"
                  max="20"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(parseInt(e.target.value, 10))}
                  disabled={running}
                  style={{
                    width: "55px",
                    padding: "3px 6px",
                    background: "var(--bg-input)",
                    border: "1px solid var(--border-default)",
                    borderRadius: "6px",
                    color: "var(--text-primary)",
                    fontSize: "0.82rem",
                  }}
                />
              </div>
            </div>

            <div style={{ display: "flex", gap: "8px" }}>
              {running && (
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={handleCancel}
                  disabled={actionLoading}
                >
                  <StopCircle size={15} /> Cancel Execution
                </button>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={!instruction.trim() || running}
                style={{ gap: "6px" }}
              >
                <Play size={15} />
                <span>{running ? "Orchestrating..." : "Execute Goal"}</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Needs Reconciliation Urgent Alert */}
      {isNeedsReconciliation && (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.12)",
            border: "1px solid var(--color-danger-border)",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <AlertTriangle size={24} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <div>
              <h4 style={{ margin: "0 0 2px 0", fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Task Interrupted — Needs External Reconciliation
              </h4>
              <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                An uncertain external failure occurred. The agent prevented blind retry to avoid duplicate non-idempotent mutations.
              </p>
            </div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={handleRetry} disabled={actionLoading}>
            <RotateCcw size={14} /> Resume & Reconcile
          </button>
        </div>
      )}

      {/* Pending Approval Urgent Banner */}
      {isAwaitingApproval && (
        <div
          style={{
            background: "rgba(245, 158, 11, 0.12)",
            border: "1px solid var(--color-warning-border)",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <ShieldAlert size={28} color="var(--color-warning)" style={{ flexShrink: 0 }} />
            <div>
              <h4 style={{ margin: "0 0 4px 0", fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Step #{activeTask.current_step_index + 1} Requires Your Cryptographic Approval
              </h4>
              <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                Tool <code>{steps[activeTask.current_step_index]?.tool_name}</code> is flagged as sensitive. Review the plan below and authorize or reject.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px" }}>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => setShowRejectModal(true)}
              disabled={actionLoading}
            >
              <X size={14} /> Reject Step
            </button>
            <button
              className="btn btn-warning btn-sm"
              onClick={handleApprove}
              disabled={actionLoading}
              style={{ background: "var(--color-warning)", color: "#000", fontWeight: 600 }}
            >
              <Check size={14} /> Sign & Approve
            </button>
          </div>
        </div>
      )}

      {/* Active Task DAG & Execution Status */}
      {activeTask ? (
        <div className="card">
          <div className="card-header">
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <h3 className="card-title">Execution Plan & DAG Steps</h3>
                <span
                  className={`badge ${
                    status === "completed" || status === "succeeded"
                      ? "badge-emerald"
                      : status === "awaiting_approval"
                      ? "badge-amber"
                      : status === "failed" || status === "needs_reconciliation"
                      ? "badge-rose"
                      : "badge-indigo"
                  }`}
                >
                  {status?.replace("_", " ")}
                </span>
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "4px" }}>
                Task ID: <code>{activeTask.id}</code> • Steps: {steps.length}
              </div>
            </div>

            <div style={{ display: "flex", gap: "8px" }}>
              <button className="btn btn-secondary btn-sm" onClick={handleOpenCheckpoints}>
                <Clock size={14} /> View Checkpoints
              </button>

              {(status === "failed" || status === "needs_reconciliation") && (
                <button className="btn btn-primary btn-sm" onClick={handleRetry} disabled={actionLoading}>
                  <RotateCcw size={14} /> Retry Task
                </button>
              )}
            </div>
          </div>

          {/* DAG Steps List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "14px" }}>
            {steps.map((step, idx) => {
              const isCurrent = idx === activeTask.current_step_index;
              const isDone = step.status === "completed" || step.status === "succeeded";
              const isFailed = step.status === "failed";
              const isWaiting = step.status === "waiting_approval" || step.status === "awaiting_approval";
              const isSkipped = step.status === "skipped";
              const isCancelled = step.status === "cancelled";
              const isRetrying = step.status === "retrying";

              return (
                <div
                  key={step.step_id || idx}
                  className={`dag-step-item ${isCurrent ? "dag-step-current" : ""} ${isWaiting ? "dag-step-awaiting" : ""}`}
                  style={{
                    background: isCurrent ? "rgba(99, 102, 241, 0.08)" : "var(--bg-surface-elevated)",
                    border: `1px solid ${
                      isCurrent
                        ? "var(--accent-primary)"
                        : isDone
                        ? "rgba(16, 185, 129, 0.35)"
                        : isFailed
                        ? "rgba(239, 68, 68, 0.4)"
                        : isWaiting
                        ? "rgba(245, 158, 11, 0.4)"
                        : "var(--border-subtle)"
                    }`,
                    borderRadius: "10px",
                    padding: "12px 16px",
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: "12px",
                    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
                  }}
                >
                  <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                    {/* Status Icon */}
                    <div style={{ marginTop: "2px" }}>
                      {isDone ? (
                        <CheckCircle2 size={18} color="var(--color-success)" />
                      ) : isFailed ? (
                        <XCircle size={18} color="var(--color-danger)" />
                      ) : isWaiting ? (
                        <AlertTriangle size={18} color="var(--color-warning)" />
                      ) : isSkipped || isCancelled ? (
                        <StopCircle size={18} color="var(--text-muted)" />
                      ) : isRetrying ? (
                        <RotateCcw size={18} color="var(--accent-primary)" className="spinning" />
                      ) : isCurrent ? (
                        <Sparkles size={18} color="var(--accent-primary)" className="spinning" />
                      ) : (
                        <div
                          style={{
                            width: "16px",
                            height: "16px",
                            borderRadius: "50%",
                            border: "2px solid var(--text-muted)",
                          }}
                        />
                      )}
                    </div>

                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                        <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--text-primary)" }}>
                          Step {idx + 1}: {step.description || step.tool_name}
                        </span>
                        <span className="badge badge-neutral" style={{ fontSize: "0.68rem" }}>
                          Tool: {step.tool_name}
                        </span>
                        {step.dependencies?.length > 0 && (
                          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                            Depends on: {step.dependencies.join(", ")}
                          </span>
                        )}
                      </div>

                      {/* Tool Parameters */}
                      {(step.tool_input || step.arguments) && (
                        <div
                          style={{
                            fontFamily: "var(--font-family-mono)",
                            fontSize: "0.75rem",
                            color: "var(--text-secondary)",
                            background: "rgba(0,0,0,0.2)",
                            padding: "4px 8px",
                            borderRadius: "4px",
                            maxWidth: "700px",
                            overflowX: "auto",
                          }}
                        >
                          Input: {JSON.stringify(step.tool_input || step.arguments)}
                        </div>
                      )}

                      {/* Error Banner on Step */}
                      {step.error && (
                        <div
                          style={{
                            marginTop: "6px",
                            fontSize: "0.78rem",
                            color: "var(--color-danger)",
                            background: "rgba(239, 68, 68, 0.08)",
                            padding: "4px 8px",
                            borderRadius: "4px",
                            display: "flex",
                            alignItems: "center",
                            gap: "6px",
                          }}
                        >
                          <AlertTriangle size={13} />
                          <span>{step.error}</span>
                        </div>
                      )}

                      {/* Output Result */}
                      {step.result && (
                        <div
                          style={{
                            marginTop: "6px",
                            fontSize: "0.78rem",
                            color: "var(--color-success)",
                            background: "rgba(16,185,129,0.06)",
                            padding: "4px 8px",
                            borderRadius: "4px",
                          }}
                        >
                          Result: {typeof step.result === "object" ? JSON.stringify(step.result) : step.result}
                        </div>
                      )}
                    </div>
                  </div>

                  <span
                    className={`badge ${
                      isDone
                        ? "badge-emerald"
                        : isFailed
                        ? "badge-rose"
                        : isWaiting
                        ? "badge-amber"
                        : isSkipped || isCancelled
                        ? "badge-neutral"
                        : isCurrent || isRetrying
                        ? "badge-indigo"
                        : "badge-neutral"
                    }`}
                  >
                    {step.status}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Failure Diagnostics Banner */}
          {(status === "failed" || status === "needs_reconciliation") && (
            <div
              style={{
                marginTop: "18px",
                background: "rgba(239, 68, 68, 0.08)",
                border: "1px solid var(--color-danger-border, rgba(239, 68, 68, 0.3))",
                borderRadius: "10px",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-danger)", fontWeight: 600, fontSize: "0.88rem", marginBottom: "8px" }}>
                <AlertTriangle size={18} />
                <span>Task Execution Diagnostics & Failure Root Cause</span>
              </div>
              <div style={{ fontSize: "0.85rem", color: "var(--text-primary)", marginBottom: "8px", lineHeight: 1.5 }}>
                {activeTask.failure_details?.safe_error_message || activeTask.result_summary || activeTask.error_message || "The task halted due to an unrecoverable failure or expired approval."}
              </div>
              {activeTask.failure_details && (
                <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "8px", paddingTop: "8px", borderTop: "1px solid rgba(239, 68, 68, 0.15)" }}>
                  <span><strong>Error Category:</strong> <code>{activeTask.failure_details.error_category}</code></span>
                  {activeTask.failure_details.failed_step_id && <span><strong>Failed Step:</strong> <code>{activeTask.failure_details.failed_step_id}</code></span>}
                  {activeTask.failure_details.tool_name && <span><strong>Tool:</strong> <code>{activeTask.failure_details.tool_name}</code></span>}
                  <span><strong>Retryable:</strong> {activeTask.failure_details.is_retryable ? "Yes (idempotent)" : "No (requires manual intervention)"}</span>
                </div>
              )}
            </div>
          )}

          {/* Final Assistant Response Synthesis */}
          {activeTask.response && (
            <div
              style={{
                marginTop: "20px",
                background: "rgba(16, 185, 129, 0.08)",
                border: "1px solid var(--color-success-border)",
                borderRadius: "10px",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-success)", fontWeight: 600, fontSize: "0.85rem", marginBottom: "8px" }}>
                <CheckCircle2 size={16} />
                <span>Execution Result Summary</span>
              </div>
              <div style={{ fontSize: "0.9rem", color: "var(--text-primary)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {activeTask.response}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card">
          <EmptyState
            icon={Bot}
            title="Agent Workspace Ready"
            description="Submit an objective above to trigger memory retrieval, plan generation, and safe tool execution."
          />
        </div>
      )}

      {/* Checkpoints History Modal */}
      {showCheckpointsModal && (
        <Modal
          isOpen={showCheckpointsModal}
          onClose={() => setShowCheckpointsModal(false)}
          title="Task Checkpoint Timeline & Snapshot States"
          footer={
            <button className="btn btn-secondary btn-sm" onClick={() => setShowCheckpointsModal(false)}>
              Close
            </button>
          }
        >
          {checkpoints && checkpoints.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {checkpoints.map((cp, idx) => (
                <div
                  key={cp.id || idx}
                  style={{
                    background: "var(--bg-surface-elevated)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    fontSize: "0.82rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      Checkpoint Step #{cp.step_index + 1}
                    </span>
                    <span className="badge badge-emerald">Fenced Gen {cp.fencing_generation || 1}</span>
                  </div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>
                    ID: <code>{cp.id}</code> • Time: {new Date(cp.created_at).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "20px 0" }}>
              No intermediate checkpoints saved for this task.
            </div>
          )}
        </Modal>
      )}

      {/* Rejection Modal */}
      {showRejectModal && (
        <Modal
          isOpen={showRejectModal}
          onClose={() => setShowRejectModal(false)}
          title="Reject Agent Step"
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowRejectModal(false)}>
                Cancel
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleReject} disabled={actionLoading}>
                Confirm Rejection
              </button>
            </>
          }
        >
          <div className="input-group">
            <label className="input-label">Reason for rejection (Optional feedback to agent)</label>
            <input
              className="input"
              type="text"
              placeholder="E.g., 'Do not create note with personal information'"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
          </div>
        </Modal>
      )}
    </div>
  );
}
