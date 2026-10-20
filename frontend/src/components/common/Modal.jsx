import React, { useEffect } from "react";
import { X } from "lucide-react";

export function Modal({ isOpen, onClose, title, children, footer, maxWidth = "580px" }) {
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape" && isOpen && onClose) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-dialog"
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
            {title}
          </h3>
          {onClose && (
            <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ padding: "4px" }}>
              <X size={16} />
            </button>
          )}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
