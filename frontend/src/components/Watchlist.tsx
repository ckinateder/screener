import { useState } from "react";
import { useForceRefreshWatchlist, useSetWatchlist, useWatchlist } from "../api/hooks";
import { changeClass, formatChange, formatPct, formatPrice } from "../lib/format";
import { useActivePane, useUi } from "../store";
import { RefreshIcon, Spinner } from "./ui/Spinner";

export function Watchlist() {
  const { setSymbol, openSearch } = useUi();
  const activeSymbol = useActivePane().symbol;
  const watchlist = useWatchlist();
  const setWatchlist = useSetWatchlist();
  const refreshAll = useForceRefreshWatchlist();
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);

  const rows = watchlist.data ?? [];
  const symbols = rows.map((r) => r.symbol);
  const busy = watchlist.isFetching || setWatchlist.isPending || refreshAll.isPending;

  const drop = (to: number) => {
    if (dragFrom !== null && dragFrom !== to) {
      const next = [...symbols];
      const [moved] = next.splice(dragFrom, 1);
      next.splice(to, 0, moved);
      setWatchlist.mutate(next);
    }
    setDragFrom(null);
    setDragOver(null);
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col border-l-4 border-border bg-bg">
      <div className="flex h-10 items-center gap-1 border-b border-border px-3">
        <h2 className="flex-1 font-medium">Watchlist</h2>
        {busy && <Spinner size={12} />}
        <button
          onClick={() => refreshAll.mutate()}
          className="rounded p-1 text-muted hover:bg-hover hover:text-text"
          title="Fetch latest prices for all symbols"
        >
          <RefreshIcon size={13} />
        </button>
        <button
          onClick={() => openSearch("add")}
          className="rounded px-1.5 py-0.5 text-lg leading-none text-muted hover:bg-hover hover:text-text"
          title="Add symbol"
        >
          +
        </button>
      </div>

      <div className="grid grid-cols-[1fr_4.5rem_4rem_4.5rem] gap-x-1 px-3 py-1 text-xs text-muted">
        <span>Symbol</span>
        <span className="text-right">Last</span>
        <span className="text-right">Chg</span>
        <span className="text-right">Chg%</span>
      </div>

      {(setWatchlist.error || watchlist.error) && (
        <p className="px-3 py-1 text-xs text-down">{(setWatchlist.error ?? watchlist.error)!.message}</p>
      )}

      <ul className="flex-1 overflow-y-auto">
        {rows.map((r, i) => (
          <li
            key={r.symbol}
            draggable
            onDragStart={() => setDragFrom(i)}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(i);
            }}
            onDragEnd={() => {
              setDragFrom(null);
              setDragOver(null);
            }}
            onDrop={() => drop(i)}
            onClick={() => setSymbol(r.symbol)}
            title={r.name ?? undefined}
            className={`group relative grid cursor-pointer grid-cols-[1fr_4.5rem_4rem_4.5rem] items-center gap-x-1 px-3 py-1.5 tabular-nums
              ${r.symbol === activeSymbol ? "bg-accent/15" : "hover:bg-hover"}
              ${dragOver === i && dragFrom !== i ? "border-t-2 border-accent" : "border-t-2 border-transparent"}
              ${dragFrom === i ? "opacity-40" : ""}`}
          >
            <span className="truncate font-medium">{r.symbol}</span>
            <span className="text-right">{formatPrice(r.last)}</span>
            <span className={`text-right ${changeClass(r.change)}`}>{formatChange(r.change)}</span>
            <span className={`text-right ${changeClass(r.change)}`}>{formatPct(r.change_pct)}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setWatchlist.mutate(symbols.filter((s) => s !== r.symbol));
              }}
              className="absolute right-1 hidden rounded bg-pane px-1.5 text-muted group-hover:block hover:text-down"
              title="Remove from watchlist"
            >
              ✕
            </button>
          </li>
        ))}
        {!watchlist.isLoading && rows.length === 0 && (
          <li className="px-3 py-6 text-center text-muted">
            Empty. Click <span className="text-text">+</span> to add symbols.
          </li>
        )}
      </ul>
    </aside>
  );
}
