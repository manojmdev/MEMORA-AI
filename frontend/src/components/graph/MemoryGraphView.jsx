import React, { useState, useMemo } from "react";
import {
  Network,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RefreshCw,
  Plus,
  X,
} from "lucide-react";
import { Modal } from "../common/Modal";
import { EmptyState, Skeleton } from "../common/EmptyState";
import { useToast } from "../layout/Toast";

const RELATIONSHIP_TYPES = [
  "uses",
  "prefers",
  "derived_from",
  "supersedes",
  "belongs_to",
  "applied_in",
  "conflicts_with",
];

export function MemoryGraphView({
  graphData,
  loading,
  onRefresh,
  onCreateRelationship,
  onDeleteRelationship,
  memories,
  sessionId: _sessionId,
}) {
  const { showToast } = useToast();
  const [selectedNode, setSelectedNode] = useState(null);
  const [filterRelType, setFilterRelType] = useState("all");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Create Relationship Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [relType, setRelType] = useState("uses");
  const [creating, setCreating] = useState(false);

  // Filter edges based on selected type
  const filteredEdges = useMemo(() => {
    if (!graphData?.edges) return [];
    if (filterRelType === "all") return graphData.edges;
    return graphData.edges.filter((e) => e.relationship_type === filterRelType);
  }, [graphData, filterRelType]);

  // Compute 2D Positions for nodes using deterministic circle layout
  const nodePositions = useMemo(() => {
    const nodes = graphData?.nodes || [];
    if (nodes.length === 0) return {};

    const positions = {};
    const width = 800;
    const height = 550;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.38;

    nodes.forEach((node, idx) => {
      const angle = (idx / nodes.length) * 2 * Math.PI;
      positions[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        ...node,
      };
    });

    return positions;
  }, [graphData]);

  const handleCanvasMouseDown = (e) => {
    if (e.target.tagName === "svg" || e.target.id === "graph-canvas") {
      setIsDraggingCanvas(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleCanvasMouseMove = (e) => {
    if (isDraggingCanvas) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleCanvasMouseUp = () => {
    setIsDraggingCanvas(false);
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleCreate = async () => {
    if (!sourceId || !targetId) {
      showToast("Please select both source and target memories", "warning");
      return;
    }
    if (sourceId === targetId) {
      showToast("Self-referential relationships are prohibited", "error");
      return;
    }

    setCreating(true);
    try {
      await onCreateRelationship({
        source_memory_id: sourceId,
        target_memory_id: targetId,
        relationship_type: relType,
      });
      showToast("Relationship created successfully", "success");
      setShowCreateModal(false);
      setSourceId("");
      setTargetId("");
    } catch (e) {
      showToast(e.message || "Failed to create relationship", "error");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteRel = async (relId) => {
    try {
      await onDeleteRelationship(relId);
      showToast("Relationship removed", "success");
    } catch (e) {
      showToast(e.message || "Failed to remove relationship", "error");
    }
  };

  const nodes = graphData?.nodes || [];

  return (
    <div
      className="view-container memory-graph-view"
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
          padding: "12px 18px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "0.86rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Relationship Filter:
          </span>
          <select
            className="select"
            value={filterRelType}
            onChange={(e) => setFilterRelType(e.target.value)}
            style={{ width: "auto", minWidth: "150px" }}
          >
            <option value="all">All Types ({graphData?.edges?.length || 0})</option>
            {RELATIONSHIP_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {/* Zoom Controls */}
          <button className="btn btn-secondary btn-sm" onClick={() => setZoom((z) => Math.min(z + 0.2, 2.5))} title="Zoom In">
            <ZoomIn size={15} />
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setZoom((z) => Math.max(z - 0.2, 0.5))} title="Zoom Out">
            <ZoomOut size={15} />
          </button>
          <button className="btn btn-secondary btn-sm" onClick={resetView} title="Reset View">
            <Maximize2 size={15} />
          </button>

          {onRefresh && (
            <button className="btn btn-ghost btn-sm" onClick={onRefresh} title="Refresh Graph Data">
              <RefreshCw size={15} className={loading ? "spinning" : ""} />
            </button>
          )}

          <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
            <Plus size={15} /> Add Relationship
          </button>
        </div>
      </div>

      {/* Main Graph Canvas & Inspector Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: selectedNode ? "1fr 340px" : "1fr",
          gap: "16px",
          height: "640px",
        }}
      >
        {/* Canvas Area */}
        <div
          className="card"
          id="graph-canvas"
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          style={{
            position: "relative",
            overflow: "hidden",
            padding: 0,
            cursor: isDraggingCanvas ? "grabbing" : "grab",
            background: "radial-gradient(circle at center, #101626 0%, #080b11 100%)",
          }}
        >
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
              <Skeleton width="60%" height="400px" borderRadius="16px" />
            </div>
          ) : nodes.length === 0 ? (
            <EmptyState
              icon={Network}
              title="No Memory Graph Nodes"
              description="Your session has no active memories or relationships. Add memories in AI Chat or link them here."
              action={
                <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
                  <Plus size={14} /> Create First Relationship
                </button>
              }
            />
          ) : (
            <svg
              width="100%"
              height="100%"
              viewBox="0 0 800 550"
              style={{
                userSelect: "none",
                display: "block",
              }}
            >
              <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                {/* Defs for arrow markers */}
                <defs>
                  <marker
                    id="arrowhead"
                    markerWidth="8"
                    markerHeight="6"
                    refX="22"
                    refY="3"
                    orient="auto"
                  >
                    <polygon points="0 0, 8 3, 0 6" fill="var(--border-focus, #6366f1)" opacity="0.8" />
                  </marker>
                </defs>

                {/* Render Edges */}
                {filteredEdges.map((edge) => {
                  const source = nodePositions[edge.source_memory_id];
                  const target = nodePositions[edge.target_memory_id];
                  if (!source || !target) return null;

                  const midX = (source.x + target.x) / 2;
                  const midY = (source.y + target.y) / 2;

                  return (
                    <g key={edge.id} className="graph-edge">
                      <line
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        stroke="var(--accent-primary, #6366f1)"
                        strokeWidth="1.8"
                        strokeOpacity="0.45"
                        strokeDasharray={edge.relationship_type === "supersedes" ? "4,4" : "none"}
                        markerEnd="url(#arrowhead)"
                      />
                      <rect
                        x={midX - 30}
                        y={midY - 10}
                        width="60"
                        height="18"
                        rx="4"
                        fill="var(--bg-surface)"
                        stroke="var(--border-subtle)"
                        strokeWidth="1"
                      />
                      <text
                        x={midX}
                        y={midY + 3}
                        fill="var(--text-muted)"
                        fontSize="9"
                        fontFamily="var(--font-family-mono)"
                        textAnchor="middle"
                        fontWeight="600"
                      >
                        {edge.relationship_type}
                      </text>
                    </g>
                  );
                })}

                {/* Render Nodes */}
                {nodes.map((node) => {
                  const pos = nodePositions[node.id];
                  if (!pos) return null;
                  const isSelected = selectedNode?.id === node.id;

                  return (
                    <g
                      key={node.id}
                      className="graph-node"
                      onClick={() => setSelectedNode(node)}
                      style={{ cursor: "pointer" }}
                    >
                      <circle
                        cx={pos.x}
                        cy={pos.y}
                        r={isSelected ? 26 : 22}
                        fill={
                          isSelected
                            ? "var(--accent-primary, #6366f1)"
                            : "var(--bg-surface-elevated, #161e33)"
                        }
                        stroke={isSelected ? "#ffffff" : "var(--border-default)"}
                        strokeWidth={isSelected ? 3 : 1.5}
                        style={{
                          filter: isSelected ? "drop-shadow(0 0 10px rgba(99,102,241,0.6))" : "none",
                          transition: "all 150ms ease",
                        }}
                      />
                      <text
                        x={pos.x}
                        y={pos.y + 4}
                        fill="#ffffff"
                        fontSize="10"
                        fontWeight="700"
                        fontFamily="var(--font-family-mono)"
                        textAnchor="middle"
                      >
                        {node.memory_key ? node.memory_key.slice(0, 4).toUpperCase() : "MEM"}
                      </text>
                      <text
                        x={pos.x}
                        y={pos.y + 36}
                        fill="var(--text-primary)"
                        fontSize="11"
                        fontWeight="600"
                        textAnchor="middle"
                      >
                        #{node.memory_key}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}

          {/* Canvas Floating Legend */}
          <div
            style={{
              position: "absolute",
              bottom: "16px",
              left: "16px",
              background: "rgba(11, 15, 25, 0.85)",
              backdropFilter: "blur(4px)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding: "6px 12px",
              fontSize: "0.72rem",
              color: "var(--text-muted)",
              display: "flex",
              gap: "12px",
            }}
          >
            <span>Nodes: {nodes.length}</span>
            <span>•</span>
            <span>Edges: {filteredEdges.length}</span>
            <span>•</span>
            <span>Pan / Click to inspect</span>
          </div>
        </div>

        {/* Selected Node Inspector Drawer */}
        {selectedNode && (
          <div
            className="card"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "14px",
              overflowY: "auto",
              position: "relative",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Node Details
              </h4>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedNode(null)}
                style={{ padding: "4px" }}
              >
                <X size={15} />
              </button>
            </div>

            <div>
              <span className="badge badge-indigo">#{selectedNode.memory_key}</span>
              <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "8px", lineHeight: 1.5 }}>
                {selectedNode.content}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.78rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Category:</span>
                <strong>{selectedNode.category}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Confidence:</span>
                <strong>{Math.round((selectedNode.confidence_score || 0) * 100)}%</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Importance:</span>
                <strong>{Math.round((selectedNode.importance_score || 0) * 100)}%</strong>
              </div>
            </div>

            {/* Connected Relationships for this node */}
            <div style={{ marginTop: "8px" }}>
              <h5 style={{ margin: "0 0 8px 0", fontSize: "0.82rem", color: "var(--text-muted)", textTransform: "uppercase" }}>
                Connected Relationships
              </h5>
              {filteredEdges.filter(
                (e) => e.source_memory_id === selectedNode.id || e.target_memory_id === selectedNode.id
              ).length === 0 ? (
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>No edges connected</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {filteredEdges
                    .filter(
                      (e) => e.source_memory_id === selectedNode.id || e.target_memory_id === selectedNode.id
                    )
                    .map((edge) => (
                      <div
                        key={edge.id}
                        style={{
                          background: "var(--bg-surface-elevated)",
                          padding: "8px 10px",
                          borderRadius: "6px",
                          fontSize: "0.78rem",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <span style={{ fontWeight: 600, color: "var(--accent-primary)" }}>
                            {edge.relationship_type}
                          </span>
                          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                            Weight: {edge.weight || 1.0}
                          </div>
                        </div>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleDeleteRel(edge.id)}
                          style={{ padding: "2px 6px", color: "var(--color-danger)" }}
                          title="Delete relationship"
                        >
                          <X size={13} />
                        </button>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Create Relationship Modal */}
      {showCreateModal && (
        <Modal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          title="Create Directed Memory Relationship"
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary btn-sm" onClick={handleCreate} disabled={creating}>
                {creating ? "Creating..." : "Establish Link"}
              </button>
            </>
          }
        >
          <div className="input-group">
            <label className="input-label">Source Memory (Subject)</label>
            <select className="select" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              <option value="">-- Select Source Memory --</option>
              {(memories || []).map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.memory_key} ({m.category}): {m.content.slice(0, 40)}...
                </option>
              ))}
            </select>
          </div>

          <div className="input-group">
            <label className="input-label">Relationship Type (Edge Predicate)</label>
            <select className="select" value={relType} onChange={(e) => setRelType(e.target.value)}>
              {RELATIONSHIP_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="input-group">
            <label className="input-label">Target Memory (Object)</label>
            <select className="select" value={targetId} onChange={(e) => setTargetId(e.target.value)}>
              <option value="">-- Select Target Memory --</option>
              {(memories || []).map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.memory_key} ({m.category}): {m.content.slice(0, 40)}...
                </option>
              ))}
            </select>
          </div>
        </Modal>
      )}
    </div>
  );
}
