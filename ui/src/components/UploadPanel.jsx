import { useState } from "react";
import { ingestCsv } from "../services/api.js";

function parsePreview(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0).slice(0, 6);
  return lines.map((line) => line.split(","));
}

export default function UploadPanel({ onIngested }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  function handleFileChange(e) {
    const f = e.target.files?.[0];
    setError(null);
    setPreview(null);
    if (!f) {
      setFile(null);
      return;
    }
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => setPreview(parsePreview(String(ev.target.result)));
    reader.readAsText(f.slice(0, 20000));
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await ingestCsv(file);
      onIngested(res, file.name);
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="panel">
      <h2>1. Upload CSV</h2>
      <div className="upload-row">
        <input type="file" accept=".csv" onChange={handleFileChange} />
        <button onClick={handleUpload} disabled={!file || uploading}>
          {uploading ? "Uploading..." : "Upload"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {preview && (
        <div className="preview-table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                {preview[0].map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.slice(1).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
