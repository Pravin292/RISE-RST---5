import { useEffect, useRef, useState } from "react";
import UploadPanel from "./components/UploadPanel.jsx";
import ProgressPanel from "./components/ProgressPanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import HealthBadge from "./components/HealthBadge.jsx";
import InsightsPanel from "./components/InsightsPanel.jsx";
import GraphExplorer from "./components/GraphExplorer.jsx";
import { getStatus, getHealth, getInsights } from "./services/api.js";

export default function App() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [insights, setInsights] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    const check = () => getHealth().then(setHealth).catch(() => setHealth(null));
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    if (pollRef.current) clearInterval(pollRef.current);

    const poll = async () => {
      try {
        const s = await getStatus(jobId);
        setStatus(s);
        if (s.status === "complete") {
          clearInterval(pollRef.current);
          const ins = await getInsights(jobId).catch(() => null);
          setInsights(ins);
        }
      } catch {
        // dataset not visible yet, keep polling
      }
    };
    poll();
    pollRef.current = setInterval(poll, 1500);
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  function handleIngested(res) {
    setInsights(null);
    setStatus(null);
    setJobId(res.job_id);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>🚀 Data In, Answers Out</h1>
        <HealthBadge health={health} />
      </header>

      <UploadPanel onIngested={handleIngested} />
      {jobId && <ProgressPanel status={status} />}
      {status?.status === "complete" && insights && <InsightsPanel insights={insights} />}
      {status?.status === "complete" && (
        <ChatPanel jobId={jobId} suggestions={insights?.suggested_questions} />
      )}
      {status?.status === "complete" && <GraphExplorer jobId={jobId} />}

      {!jobId && (
        <div className="panel">
          <h2>3. Chat With Your Data</h2>
          <p className="muted">No dataset has been uploaded yet. Upload a CSV to start chatting.</p>
        </div>
      )}
    </div>
  );
}
