import React, { useState } from "react";
import {
  Layers,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  GitMerge,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { EmptyState, Skeleton } from "../common/EmptyState";
import { useToast } from "../layout/Toast";

export function ConsolidationStudioView({
  previewData,
  loadingPreview,
  onGeneratePreview,
  onApplyConsolidation,
  sessionId: _sessionId,
}) {
  const { showToast } = useToast();
  const [minSimilarity, setMinSimilarity] = useState(0.82);
  const [maxClusterSize, setMaxClusterSize] = useState(5);
  const [confirmModalCluster, setConfirmModalCluster] = useState(null);
  const [applying, setApplying] = useState(false);

  const handleRunPreview = async () => {
    try {
      await onGeneratePreview(minSimilarity, maxClusterSize);
      showToast("Consolidation preview generated successfully", "success");
    } catch (e) {
      showToast(e.message || "Failed to generate preview", "error");
    }
  };

  const handleApply = async () => {
    if (!confirmModalCluster) return;
    setApplying(true);
    try {
      await onApplyConsolidation({
        cluster_id: confirmModalCluster.cluster_id,
        source_memory_ids: confirmModalCluster.source_memory_ids,
        synthesized_candidate: {
          category: confirmModalCluster.category || "general",
          memory_key: `consolidated_${confirmModalCluster.cluster_id.slice(0, 8)}`,
          content: confirmModalCluster.proposed_synthesis,
          confidence_score: 0.95,
          importance_score: 0.88,
          information_source: "agent_inference",
          persistence_type: "persistent",
          reason_for_storage: "Consolidated synthesis from redundant source memories",
        },
      });
      showToast("Consolidation applied atomically! Lineage edges created.", "success");
      setConfirmModalCluster(null);
      // Re-run preview to update clusters
      await onGeneratePreview(minSimilarity, maxClusterSize);
    } catch (e) {
      showToast(e.message || "Failed to apply consolidation", "error");
    } finally {
      setApplying(false);
    }
  };

  const clusters = previewData?.candidate_clusters || [];

  return (
    <div
      className="view-container consolidation-studio-view"
      style={{
        padding: "24px",
        maxWidth: "1380px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "20px",
      }}
    >
      {/* Studio Header & Parameters Card */}
      <div
        className="card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <Layers size={20} color="var(--accent-primary)" />
            <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Semantic Consolidation Studio
            </h3>
          </div>
          <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Cluster redundant, evolving, or contradictory memories into unified high-confidence facts while preserving full provenance.
          </p>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Min Sim:</span>
            <input
              type="number"
              min="0.5"
              max="0.99"
              step="0.02"
              value={minSimilarity}
              onChange={(e) => setMinSimilarity(parseFloat(e.target.value))}
              style={{
                width: "70px",
                padding: "4px 8px",
                background: "var(--bg-input)",
                border: "1px solid var(--border-default)",
                borderRadius: "6px",
                color: "var(--text-primary)",
                fontSize: "0.82rem",
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Max Cluster:</span>
            <input
              type="number"
              min="2"
              max="10"
              value={maxClusterSize}
              onChange={(e) => setMaxClusterSize(parseInt(e.target.value, 10))}
              style={{
                width: "60px",
                padding: "4px 8px",
                background: "var(--bg-input)",
                border: "1px solid var(--border-default)",
                borderRadius: "6px",
                color: "var(--text-primary)",
                fontSize: "0.82rem",
              }}
            />
          </div>

          <button
            className="btn btn-primary btn-sm"
            onClick={handleRunPreview}
            disabled={loadingPreview}
            style={{ gap: "6px" }}
          >
            <Sparkles size={14} className={loadingPreview ? "spinning" : ""} />
            <span>Scan Candidates</span>
          </button>
        </div>
      </div>

      {/* Candidates List / Empty State */}
      {loadingPreview ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <Skeleton height="180px" borderRadius="14px" />
          <Skeleton height="180px" borderRadius="14px" />
        </div>
      ) : clusters.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Layers}
            title="No Redundant Clusters Detected"
            description="Your memory store is currently clean and deduplicated at the current similarity threshold. If you have recently added new memories, click 'Scan Candidates'."
            action={
              <button className="btn btn-secondary btn-sm" onClick={handleRunPreview}>
                <RefreshCw size={14} /> Scan Now
              </button>
            }
          />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {clusters.map((cluster, cIdx) => {
            const isContradictory = cluster.is_contradictory;

            return (
              <div
                key={cluster.cluster_id || cIdx}
                className="card card-hover"
                style={{
                  borderLeft: `4px solid ${
                    isContradictory ? "var(--color-warning, #f59e0b)" : "var(--color-success, #10b981)"
                  }`,
                }}
              >
                {/* Header */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "14px",
                    flexWrap: "wrap",
                    gap: "8px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span className="badge badge-indigo">
                      Cluster {cIdx + 1} • {cluster.source_memory_ids?.length || 0} Memories
                    </span>
                    {isContradictory ? (
                      <span className="badge badge-amber">
                        <AlertTriangle size={12} /> Contradiction Detected
                      </span>
                    ) : (
                      <span className="badge badge-emerald">
                        <CheckCircle2 size={12} /> Semantic Duplicate
                      </span>
                    )}
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontFamily: "var(--font-family-mono)" }}>
                      Avg Sim: {Math.round((cluster.average_similarity || 0.85) * 100)}%
                    </span>
                  </div>

                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => setConfirmModalCluster(cluster)}
                    style={{ gap: "6px" }}
                  >
                    <GitMerge size={14} />
                    <span>Apply Consolidation</span>
                  </button>
                </div>

                {/* Synthesis Preview */}
                <div
                  style={{
                    background: "rgba(99, 102, 241, 0.07)",
                    border: "1px solid rgba(99, 102, 241, 0.2)",
                    borderRadius: "10px",
                    padding: "14px 16px",
                    marginBottom: "14px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: "var(--accent-primary)",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      marginBottom: "6px",
                    }}
                  >
                    <Sparkles size={13} />
                    <span>Proposed Unified Synthesis</span>
                  </div>
                  <div style={{ fontSize: "0.92rem", color: "var(--text-primary)", lineHeight: 1.5 }}>
                    {cluster.proposed_synthesis}
                  </div>
                </div>

                {/* Source Memories Drawer */}
                <div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      display: "block",
                      marginBottom: "8px",
                    }}
                  >
                    Source Memories To Be Consolidated:
                  </span>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "10px" }}>
                    {(cluster.source_memories || []).map((source, sIdx) => (
                      <div
                        key={source.id || sIdx}
                        style={{
                          background: "var(--bg-surface-elevated)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "8px",
                          padding: "10px 12px",
                          fontSize: "0.82rem",
                        }}
                      >
                        <div
                          style={{
                            fontWeight: 600,
                            color: "var(--text-primary)",
                            marginBottom: "4px",
                            fontFamily: "var(--font-family-mono)",
                            fontSize: "0.75rem",
                          }}
                        >
                          #{source.memory_key}
                        </div>
                        <div style={{ color: "var(--text-secondary)", lineHeight: 1.4 }}>
                          {source.content}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmModalCluster && (
        <Modal
          isOpen={!!confirmModalCluster}
          onClose={() => setConfirmModalCluster(null)}
          title="Confirm Atomic Memory Consolidation"
          footer={
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setConfirmModalCluster(null)}
                disabled={applying}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleApply}
                disabled={applying}
              >
                {applying ? "Applying..." : "Confirm & Consolidate"}
              </button>
            </>
          }
        >
          <div style={{ display: "flex", gap: "14px", alignItems: "flex-start" }}>
            <ShieldCheck size={32} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "0.85rem" }}>
              <p style={{ margin: 0 }}>
                This operation will merge <strong>{confirmModalCluster.source_memory_ids?.length || 0} source memories</strong> into a single new consolidated memory.
              </p>
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  padding: "10px 12px",
                  borderRadius: "8px",
                  color: "var(--text-primary)",
                  fontWeight: 500,
                }}
              >
                "{confirmModalCluster.proposed_synthesis}"
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", color: "var(--text-muted)", fontSize: "0.8rem", lineHeight: 1.5 }}>
                <li>Source memories will be marked as status <code>consolidated</code> and soft-deactivated.</li>
                <li>Bi-directional <code>derived_from</code> graph edges will be created connecting the new memory to original sources.</li>
                <li>Full lineage is preserved for explainability and provenance inspection.</li>
              </ul>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
