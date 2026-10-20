import React, { useState } from "react";
import {
  Menu,
  Copy,
  Check,
  Moon,
  Sun,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useToast } from "./Toast";

export function TopNav({
  title,
  subtitle,
  onOpenMobileSidebar,
  backendHealthy,
  dbConnected,
  dbPoolInfo,
  sessionId,
  theme,
  onToggleTheme,
  onNewTask,
  onRefreshData,
  refreshing,
}) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);

  const handleCopySession = () => {
    if (navigator?.clipboard && sessionId) {
      navigator.clipboard.writeText(sessionId);
      setCopied(true);
      showToast("Session ID copied to clipboard", "success", 2500);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <header
      className="app-topnav"
      style={{
        height: "64px",
        background: "var(--bg-app, #080b11)",
        borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.07))",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        position: "sticky",
        top: 0,
        zIndex: 100,
        backdropFilter: "blur(8px)",
      }}
    >
      {/* Left: Mobile Toggle & Page Title */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <button
          className="btn btn-ghost btn-sm mobile-menu-btn"
          onClick={onOpenMobileSidebar}
          style={{ padding: "6px" }}
        >
          <Menu size={20} />
        </button>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <h1
            style={{
              fontSize: "1.1rem",
              fontWeight: 700,
              color: "var(--text-primary, #f8fafc)",
              margin: 0,
              letterSpacing: "-0.01em",
            }}
          >
            {title}
          </h1>
          {subtitle && (
            <span
              style={{
                fontSize: "0.75rem",
                color: "var(--text-muted, #64748b)",
              }}
            >
              {subtitle}
            </span>
          )}
        </div>
      </div>

      {/* Right: Telemetry, Quick Actions & Session */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        {/* Backend & DB Health Indicator */}
        <div
          className="health-badge"
          title={`Backend: ${backendHealthy ? "Operational" : "Disconnected"} | Neon PostgreSQL: ${
            dbConnected ? "Connected" : "Disconnected"
          } (Pool: ${dbPoolInfo || "Active"})`}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "7px",
            padding: "5px 10px",
            borderRadius: "var(--radius-full, 9999px)",
            background: dbConnected
              ? "var(--color-success-bg, rgba(16,185,129,0.1))"
              : "var(--color-danger-bg, rgba(239,68,68,0.1))",
            border: `1px solid ${
              dbConnected
                ? "var(--color-success-border, rgba(16,185,129,0.3))"
                : "var(--color-danger-border, rgba(239,68,68,0.3))"
            }`,
            fontSize: "0.75rem",
            fontWeight: 500,
            color: dbConnected
              ? "var(--color-success, #10b981)"
              : "var(--color-danger, #ef4444)",
            cursor: "default",
          }}
        >
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: dbConnected ? "#10b981" : "#ef4444",
              boxShadow: dbConnected ? "0 0 8px #10b981" : "none",
            }}
          />
          <span className="health-label">Neon DB • Nemotron</span>
        </div>

        {/* Global Refresh Button */}
        {onRefreshData && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onRefreshData}
            disabled={refreshing}
            title="Refresh current workspace data"
            style={{ padding: "7px" }}
          >
            <RefreshCw size={15} className={refreshing ? "spinning" : ""} />
          </button>
        )}

        {/* Quick New Task Button */}
        {onNewTask && (
          <button
            className="btn btn-primary btn-sm"
            onClick={onNewTask}
            style={{ gap: "5px" }}
          >
            <Plus size={15} />
            <span>New Task</span>
          </button>
        )}

        {/* Session ID Pill */}
        <div
          onClick={handleCopySession}
          title="Click to copy session ID"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "5px 10px",
            borderRadius: "var(--radius-md, 10px)",
            background: "var(--bg-surface-elevated, #161e33)",
            border: "1px solid var(--border-default, rgba(255,255,255,0.1))",
            fontSize: "0.78rem",
            fontFamily: "var(--font-family-mono, monospace)",
            color: "var(--text-secondary, #94a3b8)",
            cursor: "pointer",
            transition: "all var(--transition-fast, 150ms)",
          }}
        >
          <span>{sessionId ? sessionId.slice(0, 14) + "..." : "session"}</span>
          {copied ? <Check size={13} color="var(--color-success, #10b981)" /> : <Copy size={13} />}
        </div>

        {/* Theme Toggle Button */}
        {onToggleTheme && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onToggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            style={{ padding: "7px" }}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}
      </div>
    </header>
  );
}
