import { useEffect, useRef, useState } from "react";
import type { ChartData, Tf } from "../api/client";
import type { Layout } from "../lib/urlState";
import { useActivePane, useUi } from "../store";
import { RefreshIcon, Spinner } from "./ui/Spinner";

interface Props {
  data: ChartData | undefined;
  refreshing: boolean;
  onRefresh: () => void;
}

export function TopBar({ data, refreshing, onRefresh }: Props) {
  const {
    active, setTf, openSearch, openSettings, watchlistOpen, toggleWatchlist,
    layout, syncRange, toggleSyncRange, lockRightEdge, toggleLockRightEdge,
  } = useUi();
  const { symbol, tf } = useActivePane();

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
      <button onClick={() => openSettings(active)} className="flex items-center gap-1.5 rounded px-2 py-1.5 hover:bg-hover">
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
        onClick={toggleLockRightEdge}
        className={`rounded p-1.5 hover:bg-hover ${lockRightEdge ? "text-accent" : "text-muted"}`}
        title={
          lockRightEdge
            ? "Scrolling stops at the latest bar (click to allow scrolling past it)"
            : "Stop scrolling past the latest bar"
        }
      >
        <RightEdgeIcon />
      </button>
      {layout !== "single" && (
        <button
          onClick={toggleSyncRange}
          className={`rounded p-1.5 hover:bg-hover ${syncRange ? "text-accent" : "text-muted"}`}
          title={syncRange ? "Time range synced between charts (click to unlink)" : "Sync time range between charts"}
        >
          <LinkIcon />
        </button>
      )}
      <LayoutMenu />
      <Divider />
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

const LAYOUT_OPTIONS: { layout: Layout; label: string }[] = [
  { layout: "single", label: "Single chart" },
  { layout: "columns", label: "Side by side" },
  { layout: "rows", label: "Stacked" },
];

function LayoutMenu() {
  const { layout, setLayout } = useUi();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} className="rounded p-1.5 hover:bg-hover" title="Chart layout">
        <LayoutIcon layout={layout} />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-44 rounded-md border border-border bg-pane py-1 shadow-2xl">
          {LAYOUT_OPTIONS.map((o) => (
            <button
              key={o.layout}
              onClick={() => {
                setLayout(o.layout);
                setOpen(false);
              }}
              className={`flex w-full items-center gap-3 px-3 py-1.5 hover:bg-hover ${layout === o.layout ? "text-accent" : ""}`}
            >
              <LayoutIcon layout={o.layout} /> {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function LayoutIcon({ layout }: { layout: Layout }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1.5" y="1.5" width="13" height="13" rx="1.5" />
      {layout === "columns" && <path d="M8 1.5v13" />}
      {layout === "rows" && <path d="M1.5 8h13" />}
    </svg>
  );
}

/** Arrow stopping at a wall: "don't scroll past the latest bar". */
const RightEdgeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M3 12h13M12 7l5 5-5 5M21 4v16" />
  </svg>
);

const LinkIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
);

const Divider = () => <span className="mx-1 h-5 w-px bg-border" />;
