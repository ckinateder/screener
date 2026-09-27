import type { ChartData, Tf } from "../api/client";
import { useUi } from "../store";
import { RefreshIcon, Spinner } from "./ui/Spinner";

interface Props {
  data: ChartData | undefined;
  refreshing: boolean;
  onRefresh: () => void;
}

export function TopBar({ data, refreshing, onRefresh }: Props) {
  const { symbol, tf, setTf, openSearch, setSettingsOpen, watchlistOpen, toggleWatchlist } = useUi();

  return (
    <header className="flex h-11 shrink-0 items-center gap-1 border-b-4 border-border bg-bg px-2">
      <button
        onClick={() => openSearch("open")}
        className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-hover"
        title="Symbol search"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <span className="font-semibold">{symbol ?? "—"}</span>
        {data?.symbol === symbol && data?.name && (
          <span className="hidden max-w-60 truncate text-muted md:inline">{data.name}</span>
        )}
      </button>

      <Divider />
      {(["D", "W"] as Tf[]).map((t) => (
        <button
          key={t}
          onClick={() => setTf(t)}
          className={`rounded px-2 py-1.5 font-medium hover:bg-hover ${tf === t ? "text-accent" : "text-text"}`}
          title={t === "D" ? "1 day" : "1 week"}
        >
          {t}
        </button>
      ))}

      <Divider />
      <button onClick={() => setSettingsOpen(true)} className="flex items-center gap-1.5 rounded px-2 py-1.5 hover:bg-hover">
        <span className="font-serif italic">ƒx</span> Indicators
      </button>

      <Divider />
      <button
        onClick={onRefresh}
        disabled={refreshing || !symbol}
        className="flex items-center gap-1.5 rounded px-2 py-1.5 hover:bg-hover disabled:opacity-60"
        title="Fetch latest bars from Yahoo"
      >
        {refreshing ? <Spinner size={14} /> : <RefreshIcon />} Refresh
      </button>

      <div className="flex-1" />
      <button
        onClick={toggleWatchlist}
        className={`rounded px-2 py-1.5 hover:bg-hover ${watchlistOpen ? "text-accent" : "text-muted"}`}
        title="Toggle watchlist"
      >
        ☰ Watchlist
      </button>
    </header>
  );
}

const Divider = () => <span className="mx-1 h-5 w-px bg-border" />;
