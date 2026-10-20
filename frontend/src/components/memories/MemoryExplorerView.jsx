import React, { useState, useMemo } from "react";
import {
  Search,
  BrainCircuit,
  Eye,
  Edit2,
  Archive,
  RefreshCw,
  Trash2,
  ShieldAlert,
  Clock,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { EmptyState, Skeleton } from "../common/EmptyState";
import { useToast } from "../layout/Toast";

export function MemoryExplorerView({
  memories,
  loading,
  onRefresh,
  onPatchMemory,
  onArchiveMemory,
  onRestoreMemory,
  onForgetMemory,
  onDeleteMemory,
  onExplainMemory,
}) {
  const { showToast } = useToast();

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active"); // 'active' | 'archived' | 'all'
  const [persistenceFilter, setPersistenceFilter] = useState("all"); // 'all' | 'persistent' | 'temporary'
  const [sourceFilter, setSourceFilter] = useState("all"); // 'all' | 'explicit' | 'inferred'
  const [sortBy, setSortBy] = useState("newest"); // 'newest' | 'oldest' | 'importance' | 'confidence'

  // Modals & Inspection State
  const [selectedMemory, setSelectedMemory] = useState(null);
  const [editingMemory, setEditingMemory] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editConfidence, setEditConfidence] = useState(0.9);
  const [confirmForgetMemory, setConfirmForgetMemory] = useState(null);
  const [confirmDeleteMemory, setConfirmDeleteMemory] = useState(null);
  const [explainData, setExplainData] = useState(null);
  const [loadingExplain, setLoadingExplain] = useState(false);

  // Derive unique categories
  const categories = useMemo(() => {
    const set = new Set();
    (memories || []).forEach((m) => {
      if (m.category) set.add(m.category);
    });
    return ["all", ...Array.from(set)];
  }, [memories]);

  // Filtered & Sorted List
  const filteredMemories = useMemo(() => {
    return (memories || [])
      .filter((m) => {
        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchKey = m.memory_key?.toLowerCase().includes(q);
          const matchContent = m.content?.toLowerCase().includes(q);
          const matchCat = m.category?.toLowerCase().includes(q);
          if (!matchKey && !matchContent && !matchCat) return false;
        }

        // Category filter
        if (selectedCategory !== "all" && m.category !== selectedCategory) {
          return false;
        }

        // Status filter
        if (statusFilter === "active" && (!m.is_active || m.is_archived)) return false;
        if (statusFilter === "archived" && !m.is_archived) return false;

        // Persistence filter
        if (persistenceFilter !== "all" && m.persistence_type !== persistenceFilter) {
          return false;
        }

        // Source filter
        if (sourceFilter === "explicit" && m.information_source !== "explicit_statement") {
          return false;
        }
        if (sourceFilter === "inferred" && m.information_source === "explicit_statement") {
          return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (sortBy === "newest") return new Date(b.created_at) - new Date(a.created_at);
        if (sortBy === "oldest") return new Date(a.created_at) - new Date(b.created_at);
        if (sortBy === "importance") return (b.importance_score || 0) - (a.importance_score || 0);
        if (sortBy === "confidence") return (b.confidence_score || 0) - (a.confidence_score || 0);
        return 0;
      });
  }, [memories, searchQuery, selectedCategory, statusFilter, persistenceFilter, sourceFilter, sortBy]);

  const currentTime = Date.now();

  const handleOpenEdit = (m) => {
    setEditingMemory(m);
    setEditContent(m.content || "");
    setEditCategory(m.category || "general");
    setEditConfidence(m.confidence_score ?? 0.9);
  };

  const handleSaveEdit = async () => {
    if (!editingMemory || !editContent.trim()) return;
    try {
      await onPatchMemory(editingMemory.id, {
        content: editContent.trim(),
        category: editCategory.trim(),
        confidence_score: parseFloat(editConfidence),
      });
      showToast("Memory updated successfully", "success");
      setEditingMemory(null);
    } catch (e) {
      showToast(e.message || "Failed to update memory", "error");
    }
  };

  const handleViewExplain = async (m) => {
    setSelectedMemory(m);
    setLoadingExplain(true);
    setExplainData(null);
    try {
      const data = await onExplainMemory(m.id);
      setExplainData(data);
    } catch {
      showToast("Failed to fetch memory explainability report", "error");
    } finally {
      setLoadingExplain(false);
    }
  };

  const handleExecuteForget = async () => {
    if (!confirmForgetMemory) return;
    try {
      await onForgetMemory(confirmForgetMemory.id);
      showToast("Memory forgotten and vector nullified", "success");
      setConfirmForgetMemory(null);
    } catch (e) {
      showToast(e.message || "Failed to forget memory", "error");
    }
  };

  const handleExecuteDelete = async () => {
    if (!confirmDeleteMemory) return;
    try {
      await onDeleteMemory(confirmDeleteMemory.id);
      showToast("Memory deleted permanently", "success");
      setConfirmDeleteMemory(null);
    } catch (e) {
      showToast(e.message || "Failed to delete memory", "error");
    }
  };

  return (
    <div className="view-container memory-explorer-view" style={{ padding: "24px", maxWidth: "1380px", margin: "0 auto" }}>
      {/* Search & Filter Header Bar */}
      <div
        className="card"
        style={{
          marginBottom: "20px",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
          gap: "14px",
        }}
      >
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          {/* Search Box */}
          <div
            style={{
              flex: "1 1 280px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "var(--bg-input)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "0 12px",
            }}
          >
            <Search size={16} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Search memories by keyword, content, or key..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                border: "none",
                background: "transparent",
                color: "var(--text-primary)",
                padding: "8px 0",
                outline: "none",
                width: "100%",
                fontSize: "0.88rem",
              }}
            />
          </div>

          {/* Status Filter */}
          <select
            className="select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ width: "auto", minWidth: "120px" }}
          >
            <option value="active">Active Only</option>
            <option value="archived">Archived Only</option>
            <option value="all">All Statuses</option>
          </select>

          {/* Persistence Filter */}
          <select
            className="select"
            value={persistenceFilter}
            onChange={(e) => setPersistenceFilter(e.target.value)}
            style={{ width: "auto", minWidth: "130px" }}
          >
            <option value="all">All Persistence</option>
            <option value="persistent">Persistent</option>
            <option value="temporary">Temporary (TTL)</option>
          </select>

          {/* Source Filter */}
          <select
            className="select"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            style={{ width: "auto", minWidth: "130px" }}
          >
            <option value="all">All Sources</option>
            <option value="explicit">Explicit Statement</option>
            <option value="inferred">Inferred</option>
          </select>

          {/* Sort By */}
          <select
            className="select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            style={{ width: "auto", minWidth: "140px" }}
          >
            <option value="newest">Sort: Newest</option>
            <option value="oldest">Sort: Oldest</option>
            <option value="importance">Highest Importance</option>
            <option value="confidence">Highest Confidence</option>
          </select>

          {onRefresh && (
            <button className="btn btn-ghost btn-sm" onClick={onRefresh} title="Refresh memory records">
              <RefreshCw size={15} className={loading ? "spinning" : ""} />
            </button>
          )}
        </div>

        {/* Category Filter Chips */}
        <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "2px" }}>
          {categories.map((cat) => (
            <button
              key={cat}
              className={`btn btn-sm ${selectedCategory === cat ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setSelectedCategory(cat)}
              style={{
                textTransform: "capitalize",
                fontSize: "0.76rem",
                borderRadius: "var(--radius-full)",
                padding: "3px 10px",
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Memory Results Grid */}
      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "16px" }}>
          <Skeleton height="160px" />
          <Skeleton height="160px" />
          <Skeleton height="160px" />
        </div>
      ) : filteredMemories.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={BrainCircuit}
            title="No Memories Found"
            description={
              searchQuery || selectedCategory !== "all" || statusFilter !== "active"
                ? "No memories matched your current filters. Try resetting search or selecting 'All'."
                : "Your memory engine has no stored items in this session. Start a conversation in AI Chat to automatically extract long-term preferences, skills, and facts."
            }
          />
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
            gap: "16px",
          }}
        >
          {filteredMemories.map((m) => {
            const isExplicit = m.information_source === "explicit_statement";
            const isExpired = m.valid_until && new Date(m.valid_until).getTime() < currentTime;

            return (
              <div
                key={m.id}
                className="card card-hover"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  opacity: m.is_archived || !m.is_active ? 0.75 : 1,
                  borderLeft: `4px solid ${
                    m.is_archived
                      ? "var(--text-muted)"
                      : isExplicit
                      ? "var(--accent-primary)"
                      : "var(--color-info)"
                  }`,
                }}
              >
                <div>
                  {/* Card Header */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: "10px",
                    }}
                  >
                    <div>
                      <span
                        style={{
                          fontFamily: "var(--font-family-mono)",
                          fontSize: "0.82rem",
                          fontWeight: 600,
                          color: "var(--text-primary)",
                        }}
                      >
                        #{m.memory_key}
                      </span>
                      <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                        <span className="badge badge-neutral">{m.category}</span>
                        <span className={`badge ${isExplicit ? "badge-emerald" : "badge-indigo"}`}>
                          {isExplicit ? "Explicit" : "Inferred"}
                        </span>
                        {m.is_archived && <span className="badge badge-rose">Archived</span>}
                        {isExpired && <span className="badge badge-amber">Expired TTL</span>}
                      </div>
                    </div>

                    <div style={{ textAlign: "right", fontSize: "0.74rem", color: "var(--text-muted)" }}>
                      <div>Conf: {Math.round((m.confidence_score || 0) * 100)}%</div>
                      <div>Imp: {Math.round((m.importance_score || 0) * 100)}%</div>
                    </div>
                  </div>

                  {/* Memory Content */}
                  <div
                    style={{
                      fontSize: "0.88rem",
                      color: "var(--text-secondary)",
                      lineHeight: 1.5,
                      marginBottom: "14px",
                    }}
                  >
                    {m.content}
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div
                  style={{
                    paddingTop: "10px",
                    borderTop: "1px solid var(--border-subtle)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                    <Clock size={12} />
                    <span>{new Date(m.created_at).toLocaleDateString()}</span>
                  </div>

                  <div style={{ display: "flex", gap: "4px" }}>
                    {/* View Details / Explain */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleViewExplain(m)}
                      title="Inspect memory provenance & lineage"
                      style={{ padding: "4px 6px" }}
                    >
                      <Eye size={13} />
                    </button>

                    {/* Edit Memory */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleOpenEdit(m)}
                      title="Edit memory content or category"
                      style={{ padding: "4px 6px" }}
                    >
                      <Edit2 size={13} />
                    </button>

                    {/* Archive or Restore */}
                    {m.is_archived ? (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => onRestoreMemory(m.id)}
                        title="Restore archived memory"
                        style={{ padding: "4px 6px", color: "var(--color-success)" }}
                      >
                        <RefreshCw size={13} />
                      </button>
                    ) : (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => onArchiveMemory(m.id)}
                        title="Archive memory (soft hide from retrieval)"
                        style={{ padding: "4px 6px" }}
                      >
                        <Archive size={13} />
                      </button>
                    )}

                    {/* Forget Memory (Zero Vector & Deactivate) */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setConfirmForgetMemory(m)}
                      title="Forget memory (GDPR deletion: nullify embedding vector)"
                      style={{ padding: "4px 6px", color: "var(--color-warning)" }}
                    >
                      <ShieldAlert size={13} />
                    </button>

                    {/* Delete Permanently */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setConfirmDeleteMemory(m)}
                      title="Delete permanently from database"
                      style={{ padding: "4px 6px", color: "var(--color-danger)" }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Edit Memory Modal */}
      {editingMemory && (
        <Modal
          isOpen={!!editingMemory}
          onClose={() => setEditingMemory(null)}
          title={`Edit Memory: #${editingMemory.memory_key}`}
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditingMemory(null)}>
                Cancel
              </button>
              <button className="btn btn-primary btn-sm" onClick={handleSaveEdit}>
                Save Changes
              </button>
            </>
          }
        >
          <div className="input-group">
            <label className="input-label">Memory Content</label>
            <textarea
              className="textarea"
              rows={4}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div className="input-group">
              <label className="input-label">Category</label>
              <input
                className="input"
                type="text"
                value={editCategory}
                onChange={(e) => setEditCategory(e.target.value)}
              />
            </div>

            <div className="input-group">
              <label className="input-label">Confidence Score ({editConfidence})</label>
              <input
                className="input"
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={editConfidence}
                onChange={(e) => setEditConfidence(e.target.value)}
              />
            </div>
          </div>
          <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", margin: "4px 0 0 0" }}>
            Note: Updating content will automatically trigger Qwen3 embedding re-generation in Neon PostgreSQL.
          </p>
        </Modal>
      )}

      {/* Explainability & Provenance Modal */}
      {selectedMemory && (
        <Modal
          isOpen={!!selectedMemory}
          onClose={() => {
            setSelectedMemory(null);
            setExplainData(null);
          }}
          title={`Memory Provenance: #${selectedMemory.memory_key}`}
          footer={
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setSelectedMemory(null);
                setExplainData(null);
              }}
            >
              Close
            </button>
          }
        >
          {loadingExplain ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <Skeleton height="30px" />
              <Skeleton height="60px" />
              <Skeleton height="30px" />
            </div>
          ) : explainData ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "14px", fontSize: "0.85rem" }}>
              <div style={{ background: "var(--bg-surface-elevated)", padding: "10px 14px", borderRadius: "8px" }}>
                <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "2px" }}>Content</div>
                <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>{explainData.content}</div>
              </div>

              <div>
                <h5 style={{ margin: "0 0 4px 0", color: "var(--accent-primary)" }}>Why Was This Extracted?</h5>
                <p style={{ margin: 0, color: "var(--text-secondary)" }}>{explainData.why_extracted}</p>
              </div>

              <div>
                <h5 style={{ margin: "0 0 4px 0", color: "var(--color-success)" }}>Why Is It Retained?</h5>
                <p style={{ margin: 0, color: "var(--text-secondary)" }}>{explainData.why_retained}</p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "0.78rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Information Source:</span>{" "}
                  <strong>{explainData.source_type}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Access Count:</span>{" "}
                  <strong>{explainData.access_count ?? 0} times</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Importance Score:</span>{" "}
                  <strong>{explainData.importance_score}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Graph Connections:</span>{" "}
                  <strong>{explainData.connected_nodes_count ?? 0} edges</strong>
                </div>
              </div>
            </div>
          ) : (
            <div>Unable to load explainability metrics for this memory record.</div>
          )}
        </Modal>
      )}

      {/* Forget Confirmation Modal */}
      {confirmForgetMemory && (
        <Modal
          isOpen={!!confirmForgetMemory}
          onClose={() => setConfirmForgetMemory(null)}
          title="Confirm Memory Forgetting"
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmForgetMemory(null)}>
                Cancel
              </button>
              <button className="btn btn-warning btn-sm" onClick={handleExecuteForget}>
                Forget Memory
              </button>
            </>
          }
        >
          <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
            <ShieldAlert size={28} color="var(--color-warning)" style={{ flexShrink: 0 }} />
            <div>
              <p style={{ margin: "0 0 8px 0" }}>
                Are you sure you want to forget <strong>#{confirmForgetMemory.memory_key}</strong>?
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                This invokes the genuine lifecycle forgetting protocol: the embedding vector is permanently nullified in Neon PostgreSQL,
                and its active status is disabled. It can no longer be retrieved by semantic or hybrid search.
              </p>
            </div>
          </div>
        </Modal>
      )}

      {/* Delete Confirmation Modal */}
      {confirmDeleteMemory && (
        <Modal
          isOpen={!!confirmDeleteMemory}
          onClose={() => setConfirmDeleteMemory(null)}
          title="Confirm Permanent Deletion"
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDeleteMemory(null)}>
                Cancel
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleExecuteDelete}>
                Delete Permanently
              </button>
            </>
          }
        >
          <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
            <Trash2 size={28} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <div>
              <p style={{ margin: "0 0 8px 0" }}>
                Permanently delete <strong>#{confirmDeleteMemory.memory_key}</strong>?
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                This completely removes the row from the database. This action cannot be undone.
              </p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
