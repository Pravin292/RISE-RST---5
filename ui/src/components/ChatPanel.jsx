import { useState } from "react";
import { askChat } from "../services/api.js";

export default function ChatPanel({ jobId, suggestions }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);

  async function send(q) {
    const text = (q ?? question).trim();
    if (!text) return;
    setAsking(true);
    setQuestion("");
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      const res = await askChat(text, jobId);
      setMessages((m) => [...m, { role: "bot", ...res }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "bot", answer: err.message, grounded: false, cypher: "", result: [] }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="panel">
      <h2>3. Chat With Your Data</h2>
      {suggestions && suggestions.length > 0 && (
        <div className="suggestions">
          {suggestions.map((s, i) => (
            <button key={i} className="chip" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="chat-window">
        {messages.length === 0 && <div className="chat-empty">Ask a question about your data.</div>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.role === "user" ? (
              <div className="chat-bubble user-bubble">{m.text}</div>
            ) : (
              <div className="chat-bubble bot-bubble">
                <div>{m.answer}</div>
                {m.cypher ? (
                  <details className="cypher-details">
                    <summary>Show Cypher &amp; Result</summary>
                    <pre className="cypher-block">{m.cypher}</pre>
                    <pre className="result-block">{JSON.stringify(m.result, null, 2)}</pre>
                  </details>
                ) : null}
                <div className={m.grounded ? "grounded-true" : "grounded-false"}>
                  {m.grounded ? "✓ Grounded in Neo4j" : "✗ Not grounded"}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <form
        className="chat-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          type="text"
          placeholder="How many rows are in Billing?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" disabled={asking}>
          {asking ? "..." : "Ask"}
        </button>
      </form>
    </div>
  );
}
