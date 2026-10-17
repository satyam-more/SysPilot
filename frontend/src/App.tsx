import { useState, useEffect } from "react";
import SettingsPage from "./pages/SettingsPage";

type Page = "settings" | "ask" | "timeline";

export default function App() {
  const [page, setPage] = useState<Page>("settings");
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    const handler = () => setSessionExpired(true);
    window.addEventListener("trailback:session-expired", handler);
    return () => window.removeEventListener("trailback:session-expired", handler);
  }, []);

  return (
    <div className="app">
      {sessionExpired && (
        <div className="session-banner">
          Session expired — restart the TrailBack backend to reconnect.
        </div>
      )}

      <div className="navbar">
        <h1>TrailBack</h1>
        <nav>
          <a
            className={page === "settings" ? "active" : ""}
            onClick={() => setPage("settings")}
          >
            Settings
          </a>
          <a
            className={page === "ask" ? "active" : ""}
            onClick={() => setPage("ask")}
          >
            Ask
          </a>
          <a
            className={page === "timeline" ? "active" : ""}
            onClick={() => setPage("timeline")}
          >
            Timeline
          </a>
        </nav>
      </div>

      {page === "settings" && <SettingsPage />}
      {page === "ask" && <div className="card"><h2>Ask — coming in Phase 10</h2></div>}
      {page === "timeline" && <div className="card"><h2>Timeline — coming in Phase 10</h2></div>}
    </div>
  );
}
