import { useState, useEffect } from "react";
import SettingsPage from "./pages/SettingsPage";
import SystemPage from "./pages/SystemPage";

type Page = "system" | "settings";

export default function App() {
  const [page, setPage] = useState<Page>("system");
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    const handler = () => setSessionExpired(true);
    window.addEventListener("syspilot:session-expired", handler);
    return () => window.removeEventListener("syspilot:session-expired", handler);
  }, []);

  return (
    <div className="app-shell">
      {sessionExpired && (
        <div className="session-banner">
          Session expired — restart the backend to reconnect.
        </div>
      )}

      {page === "system" && <SystemPage onOpenSettings={() => setPage("settings")} />}
      {page === "settings" && (
        <div className="settings-shell">
          <div className="settings-topbar">
            <button className="btn-secondary" onClick={() => setPage("system")}>
              ← Back to chat
            </button>
            <h1>Settings</h1>
          </div>
          <SettingsPage />
        </div>
      )}
    </div>
  );
}
