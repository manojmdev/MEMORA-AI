import React from "react";
import {
  LayoutDashboard,
  MessageSquare,
  Database,
  Network,
  Layers,
  Bot,
  Clock,
  Settings,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";

export const NAV_ITEMS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "chat", label: "AI Chat", icon: MessageSquare },
  { id: "memories", label: "Memories", icon: Database },
  { id: "graph", label: "Memory Graph", icon: Network },
  { id: "consolidation", label: "Consolidation Studio", icon: Layers },
  { id: "agent", label: "Agent Workspace", icon: Bot },
  { id: "tasks", label: "Task History", icon: Clock },
  { id: "settings", label: "Settings", icon: Settings },
];

export function Sidebar({
  activeNav,
  onSelectNav,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
  pendingApprovalsCount = 0,
  totalMemoriesCount = 0,
  sessionId,
}) {
  return (
    <>
      {mobileOpen && (
        <div
          className="sidebar-mobile-backdrop"
          onClick={onCloseMobile}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            backdropFilter: "blur(2px)",
            zIndex: 998,
          }}
        />
      )}
      <aside
        className={`app-sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}
        style={{
          width: collapsed ? "72px" : "260px",
          background: "var(--bg-sidebar, #0b0f19)",
          borderRight: "1px solid var(--border-subtle, rgba(255,255,255,0.07))",
          display: "flex",
          flexDirection: "column",
          transition: "width 200ms cubic-bezier(0.4, 0, 0.2, 1)",
          zIndex: 999,
          height: "100vh",
          position: "sticky",
          top: 0,
          userSelect: "none",
        }}
      >
        {/* Brand Header */}
        <div
          className="sidebar-header"
          style={{
            height: "64px",
            padding: collapsed ? "0 16px" : "0 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: collapsed ? "center" : "space-between",
            borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.07))",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              cursor: "pointer",
            }}
            onClick={() => onSelectNav("overview")}
          >
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
                boxShadow: "0 4px 12px rgba(99,102,241,0.3)",
                flexShrink: 0,
              }}
            >
              <BrainCircuit size={20} />
            </div>
            {!collapsed && (
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span
                  style={{
                    fontWeight: 700,
                    fontSize: "1.05rem",
                    letterSpacing: "-0.02em",
                    color: "var(--text-primary, #f8fafc)",
                  }}
                >
                  MEMORA AI
                </span>
                <span
                  style={{
                    fontSize: "0.68rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "var(--accent-primary, #6366f1)",
                    fontWeight: 600,
                  }}
                >
                  Memory 2.0 • Pro
                </span>
              </div>
            )}
          </div>
          {!collapsed && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={onToggleCollapse}
              title="Collapse sidebar"
              style={{ padding: "6px", color: "var(--text-muted)" }}
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>

        {/* Navigation List */}
        <nav
          className="sidebar-nav"
          style={{
            flex: 1,
            padding: "16px 10px",
            display: "flex",
            flexDirection: "column",
            gap: "4px",
            overflowY: "auto",
          }}
        >
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeNav === item.id;
            const hasPendingBadge = item.id === "agent" && pendingApprovalsCount > 0;
            const hasMemoryBadge = item.id === "memories" && totalMemoriesCount > 0;

            return (
              <button
                key={item.id}
                onClick={() => {
                  onSelectNav(item.id);
                  if (mobileOpen && onCloseMobile) onCloseMobile();
                }}
                className={`sidebar-nav-item ${isActive ? "active" : ""}`}
                title={collapsed ? item.label : undefined}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  padding: collapsed ? "10px 0" : "10px 14px",
                  justifyContent: collapsed ? "center" : "flex-start",
                  borderRadius: "8px",
                  border: "none",
                  background: isActive
                    ? "rgba(99, 102, 241, 0.14)"
                    : "transparent",
                  color: isActive
                    ? "var(--text-primary, #f8fafc)"
                    : "var(--text-secondary, #94a3b8)",
                  fontWeight: isActive ? 600 : 500,
                  fontSize: "0.88rem",
                  cursor: "pointer",
                  transition: "all var(--transition-fast, 150ms)",
                  position: "relative",
                  width: "100%",
                  textAlign: "left",
                }}
              >
                <Icon
                  size={19}
                  style={{
                    color: isActive
                      ? "var(--accent-primary, #6366f1)"
                      : "var(--text-muted, #64748b)",
                    flexShrink: 0,
                  }}
                />
                {!collapsed && (
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.label}
                  </span>
                )}
                {!collapsed && hasPendingBadge && (
                  <span
                    className="badge badge-amber"
                    style={{ fontSize: "0.68rem", padding: "1px 6px" }}
                  >
                    {pendingApprovalsCount}
                  </span>
                )}
                {!collapsed && hasMemoryBadge && (
                  <span
                    className="badge badge-neutral"
                    style={{ fontSize: "0.68rem", padding: "1px 6px" }}
                  >
                    {totalMemoriesCount}
                  </span>
                )}
                {collapsed && hasPendingBadge && (
                  <div
                    style={{
                      position: "absolute",
                      top: "6px",
                      right: "12px",
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: "var(--color-warning, #f59e0b)",
                    }}
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div
          className="sidebar-footer"
          style={{
            padding: collapsed ? "12px 8px" : "14px 16px",
            borderTop: "1px solid var(--border-subtle, rgba(255,255,255,0.07))",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          {collapsed ? (
            <button
              className="btn btn-ghost btn-sm"
              onClick={onToggleCollapse}
              title="Expand sidebar"
              style={{ width: "100%", padding: "8px 0", justifyContent: "center" }}
            >
              <ChevronRight size={16} />
            </button>
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                fontSize: "0.75rem",
                color: "var(--text-muted, #64748b)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <ShieldCheck size={14} color="var(--color-success, #10b981)" />
                <span>Session Active</span>
              </div>
              <span
                style={{
                  fontFamily: "var(--font-family-mono)",
                  background: "rgba(255,255,255,0.05)",
                  padding: "2px 6px",
                  borderRadius: "4px",
                  maxWidth: "90px",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={sessionId}
              >
                {sessionId ? sessionId.replace("session_", "") : "demo"}
              </span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
