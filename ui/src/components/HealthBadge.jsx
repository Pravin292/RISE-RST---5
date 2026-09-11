export default function HealthBadge({ health }) {
  if (!health) return <div className="health-badge health-unknown">Checking services...</div>;
  const ok = health.status === "ok";
  return (
    <div className={`health-badge ${ok ? "health-ok" : "health-bad"}`}>
      <span>Kafka {health.kafka_connected ? "✓" : "✗"}</span>
      <span>Neo4j {health.neo4j_connected ? "✓" : "✗"}</span>
      <span>API ✓</span>
    </div>
  );
}
