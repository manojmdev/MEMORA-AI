import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = "info", duration = 4000) => {
    const id = "toast_" + Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);

    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, removeToast }}>
      {children}
      <div className="toast-container" style={{
        position: "fixed",
        bottom: "24px",
        right: "24px",
        zIndex: 2000,
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        pointerEvents: "none",
        maxWidth: "420px",
      }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast toast-${t.type}`}
            style={{
              pointerEvents: "auto",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "12px 16px",
              borderRadius: "10px",
              background: "var(--bg-surface-elevated, #161e33)",
              border: `1px solid ${
                t.type === "success"
                  ? "var(--color-success-border, rgba(16,185,129,0.4))"
                  : t.type === "error"
                  ? "var(--color-danger-border, rgba(239,68,68,0.4))"
                  : t.type === "warning"
                  ? "var(--color-warning-border, rgba(245,158,11,0.4))"
                  : "var(--border-default, rgba(255,255,255,0.15))"
              }`,
              boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
              color: "var(--text-primary, #f8fafc)",
              fontSize: "0.85rem",
              lineHeight: 1.4,
              animation: "fadeIn 200ms ease-out",
            }}
          >
            {t.type === "success" && <CheckCircle2 size={18} color="var(--color-success, #10b981)" style={{ flexShrink: 0 }} />}
            {t.type === "error" && <XCircle size={18} color="var(--color-danger, #ef4444)" style={{ flexShrink: 0 }} />}
            {t.type === "warning" && <AlertTriangle size={18} color="var(--color-warning, #f59e0b)" style={{ flexShrink: 0 }} />}
            {t.type === "info" && <Info size={18} color="var(--accent-primary, #6366f1)" style={{ flexShrink: 0 }} />}
            <span style={{ flex: 1 }}>{t.message}</span>
            <button
              onClick={() => removeToast(t.id)}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--text-muted, #64748b)",
                cursor: "pointer",
                padding: "2px",
                display: "flex",
              }}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      showToast: (msg) => console.log("[Toast fallback]:", msg),
      removeToast: () => {},
    };
  }
  return context;
}
