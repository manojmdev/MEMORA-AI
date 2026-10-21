/**
 * MEMORA AI — Centralized API Client
 * Provides typed, robust HTTP interaction with error normalization,
 * session isolation, and genuine HMAC bearer token authorization.
 */

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? window.location.origin
    : "http://localhost:8000");

export function getStoredSessionId() {
  if (typeof window === "undefined") return "default-session";
  let id = localStorage.getItem("memora_session_id");
  if (!id) {
    id = "session_" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("memora_session_id", id);
  }
  return id;
}

export function setStoredSessionId(id) {
  if (typeof window === "undefined") return;
  localStorage.setItem("memora_session_id", id);
}

export function getStoredAuthToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("memora_auth_token") || "";
}

export function setStoredAuthToken(token) {
  if (typeof window === "undefined") return;
  if (!token) {
    localStorage.removeItem("memora_auth_token");
  } else {
    localStorage.setItem("memora_auth_token", token.trim());
  }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...options.headers,
  };

  const authToken = getStoredAuthToken();
  if (authToken && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  const sessionId = options.sessionId || getStoredSessionId();
  if (sessionId && !headers["X-Session-ID"]) {
    headers["X-Session-ID"] = sessionId;
  }

  const config = {
    ...options,
    headers,
  };

  try {
    const response = await fetch(url, config);

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type");
    let data = null;
    if (contentType && contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg =
        (data && typeof data === "object" && (data.detail || data.message)) ||
        (typeof data === "string" ? data : `Request failed with status ${response.status}`);
      const err = new Error(errorMsg);
      err.status = response.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (error) {
    if (error.name === "TypeError" && error.message.includes("fetch")) {
      const connErr = new Error(
        `Unable to connect to MEMORA AI backend at ${API_BASE_URL}. Ensure the FastAPI server is running.`
      );
      connErr.status = 503;
      throw connErr;
    }
    throw error;
  }
}

export const api = {
  baseUrl: API_BASE_URL,

  // System & Health
  async checkHealth() {
    return request("/health");
  },

  async getSystemInfo() {
    return request("/api/system/info");
  },

  // Conversational Memory Chat
  async chat(message, sessionId) {
    return request("/api/chat", {
      method: "POST",
      sessionId,
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  },

  // Memory Lifecycle & Search
  async listMemories(sessionId, category = null, isActive = true) {
    const params = new URLSearchParams({ session_id: sessionId });
    if (category && category !== "all") {
      params.append("category", category);
    }
    if (isActive !== null && isActive !== undefined) {
      params.append("is_active", String(isActive));
    }
    return request(`/api/memories?${params.toString()}`, { sessionId });
  },

  async getMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  async searchMemories(sessionId, q, category = null, mode = "hybrid", limit = 10) {
    const params = new URLSearchParams({
      session_id: sessionId,
      q,
      mode,
      limit: String(limit),
    });
    if (category && category !== "all") {
      params.append("category", category);
    }
    return request(`/api/memories/search?${params.toString()}`, { sessionId });
  },

  async patchMemory(sessionId, memoryId, updates) {
    return request(`/api/memories/${memoryId}?session_id=${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      sessionId,
      body: JSON.stringify(updates),
    });
  },

  async archiveMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}/archive?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
    });
  },

  async restoreMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}/restore?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
    });
  },

  async forgetMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}/forget?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
    });
  },

  async deleteMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      sessionId,
    });
  },

  async clearMemories(sessionId) {
    return request(`/api/memories?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      sessionId,
    });
  },

  async explainMemory(sessionId, memoryId) {
    return request(`/api/memories/${memoryId}/explain?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  async getDashboard(sessionId) {
    return request(`/api/memories/dashboard?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  // Relationship Graph
  async getMemoryGraph(sessionId) {
    return request(`/api/memories/graph?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  async getRelationships(sessionId, limit = 100) {
    return request(`/api/memories/relationships?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`, {
      sessionId,
    });
  },

  async createRelationship(sessionId, data) {
    return request("/api/memories/relationships", {
      method: "POST",
      sessionId,
      body: JSON.stringify({ ...data, session_id: sessionId }),
    });
  },

  async deleteRelationship(sessionId, relationshipId) {
    return request(
      `/api/memories/relationships/${relationshipId}?session_id=${encodeURIComponent(sessionId)}`,
      {
        method: "DELETE",
        sessionId,
      }
    );
  },

  // Consolidation Studio
  async previewConsolidation(sessionId, minSimilarity = 0.82, maxClusterSize = 5) {
    return request("/api/memories/consolidation/preview", {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        min_similarity: minSimilarity,
        max_cluster_size: maxClusterSize,
      }),
    });
  },

  async applyConsolidation(sessionId, data) {
    return request("/api/memories/consolidation/apply", {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        ...data,
        session_id: sessionId,
      }),
    });
  },

  // Agent Intelligence & Execution
  async runAgent(sessionId, instruction, requireApproval = false, maxSteps = 10) {
    const res = await request("/api/agent/run", {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        instruction,
        message: instruction,
        require_approval: requireApproval,
        max_steps: maxSteps,
      }),
    });
    return res.task || res;
  },

  async createAgentTask(sessionId, instruction, requireApproval = false, maxSteps = 10) {
    const res = await request("/api/agent/tasks", {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        instruction,
        message: instruction,
        require_approval: requireApproval,
        max_steps: maxSteps,
      }),
    });
    return res.task || res;
  },

  async stepAgentTask(sessionId, taskId) {
    const res = await request(`/api/agent/tasks/${taskId}/step?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
    });
    return res.task || res;
  },

  async listTasks(sessionId, limit = 50) {
    return request(`/api/agent/tasks?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`, {
      sessionId,
    });
  },

  async getTask(sessionId, taskId) {
    return request(`/api/agent/tasks/${taskId}?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  async approveTask(sessionId, taskId, approvalToken, feedback = null) {
    const res = await request(`/api/agent/tasks/${taskId}/approve?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        approval_token: approvalToken,
        feedback,
      }),
    });
    return res.task || res;
  },

  async rejectTask(sessionId, taskId, approvalToken, reason = "Rejected by user") {
    const res = await request(`/api/agent/tasks/${taskId}/reject?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        approval_token: approvalToken,
        reason,
      }),
    });
    return res.task || res;
  },

  async clarifyTask(sessionId, taskId, clarification) {
    const res = await request(`/api/agent/tasks/${taskId}/clarify?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        clarification,
      }),
    });
    return res.task || res;
  },

  async cancelTask(sessionId, taskId, reason = "Cancelled by user") {
    const res = await request(`/api/agent/tasks/${taskId}/cancel?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
      body: JSON.stringify({ reason }),
    });
    return res.task || res;
  },

  async retryTask(sessionId, taskId, fromCheckpointId = null) {
    const res = await request(`/api/agent/tasks/${taskId}/retry?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      sessionId,
      body: JSON.stringify({
        session_id: sessionId,
        from_checkpoint_id: fromCheckpointId,
      }),
    });
    return res.task || res;
  },

  async getTaskCheckpoints(sessionId, taskId) {
    return request(
      `/api/agent/tasks/${taskId}/checkpoints?session_id=${encodeURIComponent(sessionId)}`,
      { sessionId }
    );
  },

  async getTaskLogs(sessionId, taskId) {
    return request(`/api/agent/tasks/${taskId}/logs?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  // Notes & Workspace Artifacts
  async listNotes(sessionId) {
    return request(`/api/notes?session_id=${encodeURIComponent(sessionId)}`, {
      sessionId,
    });
  },

  async deleteNote(sessionId, noteId) {
    return request(`/api/notes/${noteId}?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      sessionId,
    });
  },
};
