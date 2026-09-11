export default function ProgressPanel({ status }) {
  if (!status) return null;
  const { rows_total, rows_loaded, rows_failed, status: state, filename } = status;
  const pct = rows_total > 0 ? Math.min(100, Math.round(((rows_loaded + rows_failed) / rows_total) * 100)) : 0;

  return (
    <div className="panel">
      <h2>2. Ingestion Progress</h2>
      <div className="status-line">
        <strong>{filename}</strong> — status: <span className={`badge badge-${state}`}>{state}</span>
      </div>
      <div className="progress-bar-outer">
        <div className="progress-bar-inner" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-stats">
        <span>Total: {rows_total}</span>
        <span>Loaded: {rows_loaded}</span>
        <span>Failed: {rows_failed}</span>
        <span>{pct}%</span>
      </div>
    </div>
  );
}
