import { useEffect, useState } from "react";
import { useSearch, useSetWatchlist, useWatchlist } from "../api/hooks";
import { useUi } from "../store";
import { Modal } from "./ui/Modal";
import { Spinner } from "./ui/Spinner";

const DEBOUNCE_MS = 250;

export function SymbolSearch() {
  const { search, closeSearch, setSymbol } = useUi();
  const [text, setText] = useState(search.initial);
  const [query, setQuery] = useState(search.initial.trim());
  const [active, setActive] = useState(0);
  const results = useSearch(query);
  const watchlist = useWatchlist();
  const setWatchlist = useSetWatchlist();

  useEffect(() => {
    const t = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);
  useEffect(() => setActive(0), [results.data]);

  const rows = results.data ?? [];

  const choose = (symbol: string) => {
    symbol = symbol.toUpperCase();
    if (search.mode === "open") {
      setSymbol(symbol);
      closeSearch();
      return;
    }
    const current = (watchlist.data ?? []).map((r) => r.symbol);
    if (current.includes(symbol)) return closeSearch();
    // Server fetches unstored symbols before saving; keep the dialog open to show errors.
    setWatchlist.mutate([...current, symbol], { onSuccess: closeSearch });
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      // Fall back to the raw text so exact symbols Yahoo search doesn't list still work.
      const pick = rows[active]?.symbol ?? text.trim();
      if (pick) choose(pick);
    }
  };

  return (
    <Modal title={search.mode === "open" ? "Symbol search" : "Add symbol to watchlist"} onClose={closeSearch} width="max-w-2xl">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Symbol or company name"
          className="flex-1 bg-transparent py-1 text-base uppercase outline-none placeholder:normal-case placeholder:text-muted"
        />
        {(results.isFetching || setWatchlist.isPending) && <Spinner />}
      </div>

      {setWatchlist.error && <p className="px-4 py-2 text-down">{setWatchlist.error.message}</p>}
      {results.error && <p className="px-4 py-2 text-down">{results.error.message}</p>}

      <ul className="overflow-y-auto">
        {rows.map((r, i) => (
          <li
            key={r.symbol}
            onMouseEnter={() => setActive(i)}
            onClick={() => choose(r.symbol)}
            className={`flex cursor-pointer items-center gap-3 px-4 py-2 ${i === active ? "bg-hover" : ""}`}
          >
            <span className="w-24 shrink-0 font-semibold">{r.symbol}</span>
            <span className="flex-1 truncate">{r.name}</span>
            <span className="shrink-0 text-muted">{r.type}</span>
            <span className="w-28 shrink-0 truncate text-right text-muted">{r.exchange}</span>
            <span
              className={`size-2 shrink-0 rounded-full ${r.stored ? "bg-up" : "bg-transparent"}`}
              title={r.stored ? "Already stored locally" : undefined}
            />
          </li>
        ))}
        {query && !results.isFetching && !results.error && rows.length === 0 && (
          <li className="px-4 py-6 text-center text-muted">
            No matches. Press Enter to try <span className="font-semibold text-text">{text.trim().toUpperCase()}</span> directly.
          </li>
        )}
        {!query && <li className="px-4 py-6 text-center text-muted">Start typing to search Yahoo Finance</li>}
      </ul>
    </Modal>
  );
}
