import React, { useState } from "react";
import {
  Shield,
  Download,
  RefreshCw,
  Moon,
  Sun,
  AlertTriangle,
  Info,
  Server,
  Lock,
  Trash2,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { useToast } from "../layout/Toast";
import { getStoredAuthToken, setStoredAuthToken } from "../../api/client";

export function SettingsView({
  sessionId,
  onUpdateSessionId,
  onClearSessionMemories,
  memories,
  systemInfo,
  theme,
  onToggleTheme,
}) {
  const { showToast } = useToast();
  const [tokenInput, setTokenInput] = useState(() => getStoredAuthToken());
  const [newSessionInput, setNewSessionInput] = useState(sessionId || "");
  const [showClearModal, setShowClearModal] = useState(false);
  const [clearing, setClearing] = useState(false);

  const handleSaveToken = () => {
    setStoredAuthToken(tokenInput);
    showToast(
      tokenInput.trim() ? "HMAC Bearer token updated" : "Bearer token cleared (using default session auth)",
      "success"
    );
  };

  const handleSwitchSession = () => {
    if (!newSessionInput.trim()) {
      showToast("Session ID cannot be empty", "error");
      return;
    }
    onUpdateSessionId(newSessionInput.trim());
    showToast(`Switched active session to: ${newSessionInput.trim()}`, "success");
  };

  const handleGenerateNewSession = () => {
    const generated = "session_" + Math.random().toString(36).substring(2, 9);
    setNewSessionInput(generated);
    onUpdateSessionId(generated);
    showToast(`Generated new isolated session: ${generated}`, "success");
  };

  const handleExportMemories = () => {
    if (!memories || memories.length === 0) {
      showToast("No memories available to export", "warning");
      return;
    }
    const blob = new Blob([JSON.stringify(memories, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `memora_memories_${sessionId}_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Memories exported successfully", "success");
  };

  const handleExecuteClear = async () => {
    setClearing(true);
    try {
      await onClearSessionMemories();
      showToast("All memories for this session have been deleted", "success");
      setShowClearModal(false);
    } catch (e) {
      showToast(e.message || "Failed to clear memories", "error");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div
      className="view-container settings-view"
      style={{
        padding: "24px",
        maxWidth: "980px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
      }}
    >
      {/* 1. Session & Identity Section */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            <Shield size={18} color="var(--accent-primary)" />
            <span>Session Ownership & Identity Boundary</span>
          </h3>
          <span className="badge badge-neutral">Client Scoped</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            MEMORA AI uses strict session scoping to isolate memories, relationship graphs, notes, and agent execution plans in Neon PostgreSQL.
          </p>

          <div className="input-group" style={{ marginBottom: 0 }}>
            <label className="input-label">Current Session ID</label>
            <div style={{ display: "flex", gap: "10px" }}>
              <input
                className="input"
                type="text"
                value={newSessionInput}
                onChange={(e) => setNewSessionInput(e.target.value)}
                style={{ fontFamily: "var(--font-family-mono)" }}
              />
              <button className="btn btn-secondary btn-sm" onClick={handleSwitchSession}>
                Switch Session
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleGenerateNewSession}>
                <RefreshCw size={14} /> New
              </button>
            </div>
          </div>

          <div
            style={{
              background: "rgba(99, 102, 241, 0.08)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              borderRadius: "8px",
              padding: "10px 14px",
              fontSize: "0.78rem",
              color: "var(--text-secondary)",
              display: "flex",
              alignItems: "flex-start",
              gap: "8px",
            }}
          >
            <Info size={16} color="var(--accent-primary)" style={{ flexShrink: 0, marginTop: "2px" }} />
            <span>
              <strong>Identity Note:</strong> A browser-generated session ID isolates data between browser profiles and devices. In strict production deployments, external OAuth/OIDC or genuine HMAC bearer credentials are required to associate sessions with verified user accounts.
            </span>
          </div>
        </div>
      </div>

      {/* 2. Authentication & HMAC Bearer Tokens */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            <Lock size={18} color="var(--color-warning)" />
            <span>Authentication Credentials (HMAC Bearer)</span>
          </h3>
          <span className={`badge ${systemInfo?.auth_mode?.includes("Strict") ? "badge-emerald" : "badge-amber"}`}>
            {systemInfo?.auth_mode || "Development / Demo"}
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            Configure an optional signed Bearer token. When present, the frontend client includes this token in the <code>Authorization: Bearer &lt;token&gt;</code> header on all REST calls.
          </p>

          <div className="input-group" style={{ marginBottom: 0 }}>
            <label className="input-label">HMAC Signed Bearer Token</label>
            <div style={{ display: "flex", gap: "10px" }}>
              <input
                className="input"
                type="password"
                placeholder="Paste signed token (<base64_payload>.<hmac_signature>)..."
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                style={{ fontFamily: "var(--font-family-mono)" }}
              />
              <button className="btn btn-primary btn-sm" onClick={handleSaveToken}>
                Save Token
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 3. System & Model Telemetry */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            <Server size={18} color="var(--color-success)" />
            <span>Live System & Model Configuration</span>
          </h3>
          <span className="badge badge-emerald">Verified DB</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "0.82rem" }}>
          <div style={{ padding: "8px 12px", background: "var(--bg-surface-elevated)", borderRadius: "8px" }}>
            <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "2px" }}>LLM Inference</span>
            <strong style={{ color: "var(--text-primary)" }}>{systemInfo?.llm_model || "NVIDIA Nemotron-3_5-Lightning"}</strong>
          </div>

          <div style={{ padding: "8px 12px", background: "var(--bg-surface-elevated)", borderRadius: "8px" }}>
            <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "2px" }}>Embedding Model</span>
            <strong style={{ color: "var(--text-primary)" }}>
              {systemInfo?.embedding_model || "Qwen/Qwen3-Embedding-8B"} ({systemInfo?.embedding_dim || 4096}-d)
            </strong>
          </div>

          <div style={{ padding: "8px 12px", background: "var(--bg-surface-elevated)", borderRadius: "8px" }}>
            <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "2px" }}>Database Engine</span>
            <strong style={{ color: "var(--text-primary)" }}>{systemInfo?.database_provider || "Neon Lakebase Postgres (pgvector)"}</strong>
          </div>

          <div style={{ padding: "8px 12px", background: "var(--bg-surface-elevated)", borderRadius: "8px" }}>
            <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "2px" }}>Worker Lease Identity</span>
            <code style={{ fontSize: "0.74rem" }}>
              {systemInfo?.worker_id ? systemInfo.worker_id.slice(0, 24) + "..." : "worker-local"}
            </code>
          </div>
        </div>
      </div>

      {/* 4. Application Preferences */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            {theme === "dark" ? <Moon size={18} color="var(--accent-primary)" /> : <Sun size={18} color="var(--color-warning)" />}
            <span>Interface Preferences</span>
          </h3>
          <span className="badge badge-neutral">{theme.toUpperCase()} MODE</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--text-primary)" }}>
              Visual Theme
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Switch between luxury deep charcoal dark mode and clean high-contrast light mode.
            </div>
          </div>
          {onToggleTheme && (
            <button className="btn btn-secondary btn-sm" onClick={onToggleTheme}>
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />} Switch to {theme === "dark" ? "Light" : "Dark"}
            </button>
          )}
        </div>
      </div>

      {/* 5. Privacy, Export & Danger Zone */}
      <div className="card" style={{ borderColor: "var(--color-danger-border)" }}>
        <div className="card-header">
          <h3 className="card-title" style={{ color: "var(--color-danger)" }}>
            <Trash2 size={18} color="var(--color-danger)" />
            <span>Memory Privacy & Data Controls</span>
          </h3>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--text-primary)" }}>
                Export Session Knowledge
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Download all active and archived memories as a verified JSON file.
              </div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={handleExportMemories}>
              <Download size={14} /> Export JSON
            </button>
          </div>

          <div
            style={{
              paddingTop: "14px",
              borderTop: "1px solid var(--border-subtle)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "10px",
            }}
          >
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--color-danger)" }}>
                Clear All Memories in Session
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Permanently purge all memory rows, embeddings, and relationship edges for <code>{sessionId}</code>.
              </div>
            </div>
            <button className="btn btn-danger btn-sm" onClick={() => setShowClearModal(true)}>
              <Trash2 size={14} /> Clear Session Memories
            </button>
          </div>
        </div>
      </div>

      {/* Clear Confirmation Modal */}
      {showClearModal && (
        <Modal
          isOpen={showClearModal}
          onClose={() => setShowClearModal(false)}
          title="Confirm Purge of All Session Memories"
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowClearModal(false)}>
                Cancel
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleExecuteClear} disabled={clearing}>
                {clearing ? "Purging..." : "Confirm Purge"}
              </button>
            </>
          }
        >
          <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
            <AlertTriangle size={32} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <div>
              <p style={{ margin: "0 0 8px 0" }}>
                Are you sure you want to delete ALL memories belonging to session <strong>{sessionId}</strong>?
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                This invokes <code>DELETE /api/memories</code> against Neon PostgreSQL. All active, temporary, archived, and relationship graph records for this session will be removed.
              </p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
