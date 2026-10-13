import { useState } from "react";
import { BrainCircuit, Send, Sparkles, User } from "lucide-react";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm MEMORA AI. I'm connected to NVIDIA Nemotron through Nebius. Let's start building your intelligent memory workspace."
    }
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const message = input.trim();

    if (!message || loading) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: message }
    ]);

    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ message })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to generate a response."
        );
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          model: data.model
        }
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${error.message}`
        }
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="navbar">
        <div className="brand">
          <div className="brand-icon">
            <BrainCircuit size={23} />
          </div>

          <div>
            <h2>MEMORA<span> AI</span></h2>
            <p>Personal Intelligence Workspace</p>
          </div>
        </div>

        <div className="connection">
          <span className="status-dot"></span>
          Nebius Connected
        </div>
      </header>

      <main className="workspace">
        <section className="welcome">
          <div className="sparkle">
            <Sparkles size={22} />
          </div>

          <p className="eyebrow">YOUR PERSONAL AI WORKSPACE</p>

          <h1>
            Intelligence that
            <br />
            <span>remembers.</span>
          </h1>

          <p className="subtitle">
            A new kind of AI assistant, powered by NVIDIA
            Nemotron and Nebius.
          </p>
        </section>

        <section className="chat-panel">
          <div className="chat-heading">
            <div>
              <h3>AI Workspace</h3>
              <p>Test your first MEMORA interaction</p>
            </div>

            <span className="model-label">NEMOTRON</span>
          </div>

          <div className="messages">
            {messages.map((msg, index) => (
              <div
                className={`message ${msg.role}`}
                key={index}
              >
                <div className="avatar">
                  {msg.role === "assistant" ? (
                    <BrainCircuit size={18} />
                  ) : (
                    <User size={18} />
                  )}
                </div>

                <div className="message-content">
                  <span className="sender">
                    {msg.role === "assistant"
                      ? "MEMORA AI"
                      : "YOU"}
                  </span>

                  <p>{msg.content}</p>

                  {msg.model && (
                    <small>Powered by {msg.model}</small>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="typing">
                <span></span>
                <span></span>
                <span></span>
                MEMORA is thinking...
              </div>
            )}
          </div>

          <div className="input-area">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask MEMORA anything..."
              disabled={loading}
            />

            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </div>

          <p className="disclaimer">
            Day 1 prototype · Persistent memory is coming next.
          </p>
        </section>
      </main>
    </div>
  );
}

export default App;
