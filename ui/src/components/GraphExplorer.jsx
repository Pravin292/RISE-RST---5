import { useEffect, useState } from "react";
import { getGraph } from "../services/api.js";

const WIDTH = 640;
const HEIGHT = 420;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };

export default function GraphExplorer({ jobId }) {
  const [graph, setGraph] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId) return;
    getGraph(jobId, 40)
      .then(setGraph)
      .catch((err) => setError(err.message));
  }, [jobId]);

  if (error) return <div className="panel"><h2>Graph Explorer</h2><div className="error-box">{error}</div></div>;
  if (!graph) return null;

  const rowNodes = graph.nodes.filter((n) => n.type === "Row");
  const radius = Math.min(WIDTH, HEIGHT) / 2 - 40;
  const positioned = rowNodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(rowNodes.length, 1);
    return {
      ...n,
      x: CENTER.x + radius * Math.cos(angle),
      y: CENTER.y + radius * Math.sin(angle),
    };
  });

  return (
    <div className="panel">
      <h2>Graph Explorer</h2>
      <p className="muted">Dataset node with up to 40 sampled Row nodes.</p>
      <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="graph-svg">
        {positioned.map((n) => (
          <line
            key={`edge-${n.id}`}
            x1={CENTER.x}
            y1={CENTER.y}
            x2={n.x}
            y2={n.y}
            stroke="#cbd5e1"
            strokeWidth="1"
          />
        ))}
        {positioned.map((n) => (
          <circle
            key={n.id}
            cx={n.x}
            cy={n.y}
            r={8}
            fill={selected?.id === n.id ? "#2563eb" : "#60a5fa"}
            stroke="#1e3a8a"
            strokeWidth="1"
            onClick={() => setSelected(n)}
            style={{ cursor: "pointer" }}
          />
        ))}
        <circle cx={CENTER.x} cy={CENTER.y} r={16} fill="#f97316" stroke="#7c2d12" strokeWidth="1.5" />
        <text x={CENTER.x} y={CENTER.y + 30} textAnchor="middle" fontSize="11" fill="#334155">
          Dataset
        </text>
      </svg>
      {selected && (
        <div className="graph-detail">
          <strong>{selected.label}</strong>
          <pre>{JSON.stringify(selected.props, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
