import { useEffect, useState } from "react";
import { api, Dictionaries } from "./api";
import CreateCampaign from "./components/CreateCampaign";
import CampaignList from "./components/CampaignList";
import CampaignEditor from "./components/CampaignEditor";

type Route = { page: "new" } | { page: "campaigns" } | { page: "editor"; id: number };

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const match = hash.match(/^campaigns\/(\d+)/);
  if (match) return { page: "editor", id: Number(match[1]) };
  if (hash.startsWith("campaigns")) return { page: "campaigns" };
  return { page: "new" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash);
  const [dicts, setDicts] = useState<Dictionaries | null>(null);
  const [dictError, setDictError] = useState("");

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api.dictionaries().then(setDicts).catch((e) => setDictError(e.message));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Keitaro wrapper</span>
        <nav>
          <a href="#/new" className={route.page === "new" ? "active" : ""}>
            Новая кампания
          </a>
          <a href="#/campaigns" className={route.page !== "new" ? "active" : ""}>
            Редактор кампаний
          </a>
        </nav>
        {dicts?.mock && (
          <span className="badge warn" title="KEITARO_MOCK=true — запросы идут в фейковый Keitaro">
            MOCK
          </span>
        )}
      </header>

      {dictError && <div className="alert error">Не удалось загрузить справочники: {dictError}</div>}

      <main>
        {route.page === "new" && <CreateCampaign dicts={dicts} />}
        {route.page === "campaigns" && <CampaignList prefix={dicts?.campaign_prefix ?? ""} />}
        {route.page === "editor" && <CampaignEditor campaignId={route.id} />}
      </main>
    </div>
  );
}
