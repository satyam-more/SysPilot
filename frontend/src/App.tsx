import { useState, useEffect } from "react";
import SettingsPage from "./pages/SettingsPage";
import SystemPage from "./pages/SystemPage";

type Page = "system" | "settings";

export default function App() {
  const [page, setPage] = useState<Page>("system");
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
          Session expired — restart the backend to reconnect.
        </div>
      )}

      <div className="navbar">
        <h1>System Health Assistant</h1>
        <nav>
          <a className={page === "system" ? "active" : ""} onClick={() => setPage("system")}>
            Assistant
          </a>
          <a className={page === "settings" ? "active" : ""} onClick={() => setPage("settings")}>
            Settings
          </a>
        </nav>
      </div>

      {page === "system" && <SystemPage />}
      {page === "settings" && <SettingsPage />}
    </div>
  );
}
