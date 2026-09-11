import React, { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000';

export default function App() {
  // System Health State
  const [health, setHealth] = useState({ status: 'checking', kafka_connected: false, neo4j_connected: false });

  // Ingestion State
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [currentJob, setCurrentJob] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [previewData, setPreviewData] = useState([]);
  const [healthMetrics, setHealthMetrics] = useState(null);

  // Chat State
  const [question, setQuestion] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      sender: 'assistant',
      answer: 'Hello! I am your rule-based Neo4j graph assistant. Upload a CSV file above to start querying your data without any external LLMs.',
      cypher: null,
      result: [],
      grounded: false
    }
  ]);

  // Schema state for dynamic suggested questions
  const [activeProperties, setActiveProperties] = useState([]);

  // Auto-scroll chat history
  const chatEndRef = useRef(null);
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Poll Health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        setHealth(data);
      } catch (err) {
        setHealth({ status: 'offline', kafka_connected: false, neo4j_connected: false });
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  // Poll Schema
  const fetchSchema = async () => {
    try {
      const res = await fetch(`${API_BASE}/schema`);
      const data = await res.json();
      if (data.properties) {
        setActiveProperties(data.properties);
      }
    } catch (e) {
      console.warn("Schema fetch error:", e);
    }
  };

  useEffect(() => {
    fetchSchema();
  }, []);

  // Poll Job Status if job active
  useEffect(() => {
    if (!currentJob) return;

    const pollStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/status?job_id=${currentJob.job_id}`);
        if (res.ok) {
          const data = await res.json();
          setJobStatus(data);
          if (data.status === 'complete' || data.status === 'failed') {
            fetchSchema(); // update available schema props
          }
        }
      } catch (err) {
        console.error("Status poll error:", err);
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 1000);
    return () => clearInterval(interval);
  }, [currentJob]);

  // Handle File Selection
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setUploadError(null);
    }
  };

  // Handle File Upload
  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setJobStatus(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      setCurrentJob(data);
      setPreviewData(data.preview || []);
      setHealthMetrics(data.health_metrics || null);
      setJobStatus({
        job_id: data.job_id,
        status: 'queued',
        rows_total: data.rows_received,
        rows_loaded: 0,
        rows_failed: 0
      });
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  };

  // Handle Send Chat
  const handleSendChat = async (qText) => {
    const textToSend = qText || question;
    if (!textToSend || !textToSend.trim()) return;

    // Append user message
    const userMsg = { sender: 'user', answer: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion('');
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: textToSend }),
      });

      const data = await res.json();
      const assistantMsg = {
        sender: 'assistant',
        answer: data.answer,
        cypher: data.cypher,
        result: data.result,
        grounded: data.grounded
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          answer: 'Error communicating with backend service.',
          cypher: null,
          result: [],
          grounded: false
        }
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Generate Suggested Questions (WOW Feature 2)
  const generateSuggestedQuestions = () => {
    const suggestions = ['How many rows are there?'];
    
    if (activeProperties.includes('department')) {
      suggestions.push('What are the unique departments?');
      suggestions.push('How many people are in Billing?');
    } else if (activeProperties.length > 0) {
      suggestions.push(`What are the unique ${activeProperties[0]}s?`);
    }

    if (activeProperties.includes('age')) {
      suggestions.push('What is the average age?');
    }
    if (activeProperties.includes('salary')) {
      suggestions.push('What is the maximum salary?');
      suggestions.push('What is the total sum of salary?');
    }

    return suggestions;
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-title-box">
          <div className="header-icon">🚀</div>
          <div>
            <h1 className="header-title">Data In, Answers Out</h1>
            <p className="header-subtitle">CSV → Kafka → Neo4j Intelligence Pipeline</p>
          </div>
        </div>

        <div className="health-status-bar">
          <div className="status-badge">
            <span>API:</span>
            <span className={`dot ${health.status === 'ok' || health.status === 'degraded' ? 'online' : 'offline'}`} />
          </div>
          <div className="status-badge">
            <span>Kafka:</span>
            <span className={`dot ${health.kafka_connected ? 'online' : 'offline'}`} />
          </div>
          <div className="status-badge">
            <span>Neo4j:</span>
            <span className={`dot ${health.neo4j_connected ? 'online' : 'offline'}`} />
          </div>
        </div>
      </header>

      {/* Main Dashboard Grid */}
      <main className="dashboard-grid">
        {/* Left Column: Upload & Ingestion */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Upload Card */}
          <div className="card">
            <h2 className="card-title">📁 CSV Ingestion</h2>
            
            <form onSubmit={handleUpload} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <label className="upload-dropzone">
                <input type="file" accept=".csv" onChange={handleFileChange} style={{ display: 'none' }} />
                <span style={{ fontSize: '2rem' }}>📄</span>
                <div>
                  <strong>{file ? file.name : 'Click or Drag CSV here'}</strong>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Supports dynamic CSV structure'}
                  </p>
                </div>
              </label>

              {uploadError && (
                <div style={{ color: 'var(--accent-rose)', fontSize: '0.85rem', padding: '8px 12px', background: 'rgba(244, 63, 94, 0.1)', borderRadius: '6px' }}>
                  ⚠️ {uploadError}
                </div>
              )}

              <button type="submit" className="btn-primary" disabled={!file || uploading}>
                {uploading ? 'Processing & Streaming to Kafka...' : 'Upload & Stream CSV'}
              </button>
            </form>

            {/* Pipeline Visualization */}
            <div className="pipeline-flow">
              <div className="pipeline-node">
                <span>CSV</span>
                <span className="dot online" />
              </div>
              <span className="pipeline-arrow">→</span>
              <div className="pipeline-node">
                <span>FastAPI</span>
                <span className={`dot ${health.status !== 'offline' ? 'online' : 'offline'}`} />
              </div>
              <span className="pipeline-arrow">→</span>
              <div className="pipeline-node">
                <span>Kafka</span>
                <span className={`dot ${health.kafka_connected ? 'online' : 'offline'}`} />
              </div>
              <span className="pipeline-arrow">→</span>
              <div className="pipeline-node">
                <span>Loader</span>
                <span className={`dot ${health.neo4j_connected ? 'online' : 'offline'}`} />
              </div>
              <span className="pipeline-arrow">→</span>
              <div className="pipeline-node">
                <span>Neo4j</span>
                <span className={`dot ${health.neo4j_connected ? 'online' : 'offline'}`} />
              </div>
            </div>

            {/* Progress Bar */}
            {jobStatus && (
              <div className="progress-container">
                <div className="progress-stats">
                  <span>Job: {jobStatus.job_id} ({jobStatus.status})</span>
                  <span>{jobStatus.rows_loaded} / {jobStatus.rows_total} rows</span>
                </div>
                <div className="progress-track">
                  <div 
                    className="progress-fill" 
                    style={{ width: `${jobStatus.rows_total > 0 ? (jobStatus.rows_loaded / jobStatus.rows_total) * 100 : 0}%` }}
                  />
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Loaded: {jobStatus.rows_loaded}</span>
                  <span>Failed: {jobStatus.rows_failed}</span>
                  <span>Idempotency: MERGE Active</span>
                </div>
              </div>
            )}
          </div>

          {/* WOW Feature 1: Data Health Score Card */}
          {healthMetrics && (
            <div className="card">
              <h2 className="card-title">📊 Data Health Score (WOW Feature)</h2>
              <div className="health-score-card">
                <div className="score-badge">
                  {healthMetrics.health_score}
                </div>
                <div className="score-details">
                  <div><strong>Total Rows:</strong> {healthMetrics.total_rows}</div>
                  <div><strong>Columns:</strong> {healthMetrics.columns_count}</div>
                  <div><strong>Missing Cells:</strong> {healthMetrics.missing_cells}</div>
                  <div><strong>Duplicate Rows:</strong> {healthMetrics.duplicate_rows}</div>
                </div>
              </div>
            </div>
          )}

          {/* CSV Preview Table */}
          {previewData.length > 0 && (
            <div className="card">
              <h2 className="card-title">🔍 CSV Preview (First 5 Rows)</h2>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(previewData[0]).map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((val, j) => (
                          <td key={j}>{String(val)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* WOW Feature 3: Graph Explorer Schema Summary */}
          <div className="card">
            <h2 className="card-title">🕸️ Neo4j Graph Explorer</h2>
            <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}>
              <div style={{ color: 'var(--accent-cyan)', fontWeight: 'bold' }}>(:Dataset) -[:HAS_ROW]-> (:Row)</div>
              <div style={{ marginTop: '8px', color: 'var(--text-secondary)' }}>
                Active Graph Properties: {activeProperties.length > 0 ? activeProperties.join(', ') : 'No data ingested yet'}
              </div>
            </div>
          </div>

        </div>

        {/* Right Column: Chat Interface */}
        <div className="card chat-container">
          <h2 className="card-title">🤖 Grounded Graph Chatbot (Rule-Based)</h2>

          {/* Suggested Questions (WOW Feature 2) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>💡 TRY ASKING:</span>
            <div className="suggested-questions">
              {generateSuggestedQuestions().map((q, idx) => (
                <button key={idx} className="suggestion-pill" onClick={() => handleSendChat(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* Chat History */}
          <div className="chat-history">
            {messages.map((msg, index) => (
              <div key={index} className={`chat-bubble ${msg.sender}`}>
                <div>{msg.answer}</div>

                {/* Grounded Tag */}
                {msg.sender === 'assistant' && msg.cypher !== null && (
                  <span className={`grounded-tag ${msg.grounded ? 'true' : 'false'}`}>
                    {msg.grounded ? '✓ Grounded in Neo4j' : '❌ Grounded: FALSE'}
                  </span>
                )}

                {/* Expandable Cypher & Raw Results Drawer */}
                {msg.cypher && (
                  <div className="details-drawer">
                    <div className="drawer-header">Generated Cypher:</div>
                    <div className="code-block">{msg.cypher}</div>
                    
                    {msg.result && msg.result.length > 0 && (
                      <>
                        <div className="drawer-header" style={{ marginTop: '8px' }}>Neo4j Result:</div>
                        <div className="code-block">{JSON.stringify(msg.result, null, 2)}</div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
            {chatLoading && (
              <div className="chat-bubble assistant">
                <span style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>Executing Cypher on Neo4j...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Chat Input */}
          <div className="chat-input-row">
            <input
              type="text"
              className="chat-input"
              placeholder="Ask a question about your uploaded CSV..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
            />
            <button className="btn-primary" onClick={() => handleSendChat()} disabled={chatLoading}>
              Ask
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
