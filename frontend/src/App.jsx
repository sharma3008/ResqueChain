import React, { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function severityColor(label) {
  switch (label) {
    case "CRITICAL":
      return "#ef4444";
    case "HIGH":
      return "#f97316";
    case "MEDIUM":
      return "#eab308";
    default:
      return "#22c55e";
  }
}

export default function App() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/triage`);
      const data = await res.json();
      setCases(data.items || []);
    } catch (err) {
      console.error("Failed to fetch triage data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const id = setInterval(loadData, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#020817",
      color: "#e5e7eb",
      padding: "24px",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    }}>
      <h1 style={{ fontSize: "28px", fontWeight: 600, marginBottom: "8px" }}>
        🚑 ResQChain — Live Triage Dashboard
      </h1>
      <p style={{ marginBottom: "20px", color: "#9ca3af" }}>
        Streaming AI-assessed emergencies from verified responders into a tamper-evident ledger.
      </p>

      {loading && <p>Loading triage data...</p>}

      {!loading && cases.length === 0 && (
        <p>No triage cases yet. Trigger one via the API.</p>
      )}

      {!loading && cases.length > 0 && (
        <div style={{
          marginTop: "12px",
          borderRadius: "16px",
          padding: "16px",
          background: "#020817",
          boxShadow: "0 18px 60px rgba(15,23,42,0.9)",
          border: "1px solid #111827"
        }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #111827" }}>
                <th style={{ padding: "8px" }}>Case Hash</th>
                <th style={{ padding: "8px" }}>Patient</th>
                <th style={{ padding: "8px" }}>Severity</th>
                <th style={{ padding: "8px" }}>Incident</th>
                <th style={{ padding: "8px" }}>Location</th>
                <th style={{ padding: "8px" }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #111827" }}>
                  <td style={{ padding: "8px", fontFamily: "monospace", fontSize: "11px", color: "#6b7280" }}>
                    {c.case_hash ? c.case_hash.slice(0, 10) + "..." : "-"}
                  </td>
                  <td style={{ padding: "8px" }}>{c.patient_id || "-"}</td>
                  <td style={{ padding: "8px", fontWeight: 600, color: severityColor(c.severity_label) }}>
                    {c.severity_label || "-"} ({c.severity_score})
                  </td>
                  <td style={{ padding: "8px" }}>{c.incident_type}</td>
                  <td style={{ padding: "8px" }}>
                    {c.location
                      ? `${c.location.lat?.toFixed(3)}, ${c.location.lon?.toFixed(3)}`
                      : "-"}
                  </td>
                  <td style={{ padding: "8px", color: "#9ca3af" }}>
                    {c.timestamp
                      ? new Date(c.timestamp * 1000).toLocaleTimeString()
                      : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
