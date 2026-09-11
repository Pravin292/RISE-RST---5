export default function InsightsPanel({ insights }) {
  if (!insights) return null;
  const { health_score, columns } = insights;
  const color = health_score >= 80 ? "#2e7d32" : health_score >= 50 ? "#f9a825" : "#c62828";

  return (
    <div className="panel">
      <h2>Data Health Score</h2>
      <div className="health-score-row">
        <div className="health-gauge" style={{ borderColor: color, color }}>
          {health_score}
        </div>
        <div className="health-columns">
          {columns.map((c) => (
            <div key={c.column} className="health-col-row">
              <span className="col-name">{c.column}</span>
              <div className="mini-bar-outer">
                <div
                  className="mini-bar-inner"
                  style={{ width: `${100 - c.missing_pct}%` }}
                />
              </div>
              <span className="col-meta">
                {c.missing_pct}% missing &middot; {c.unique_count} unique
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
