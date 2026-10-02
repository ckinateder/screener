import { useState } from "react";
import type { ChecklistScore, SectorEtf } from "../api/client";
import { useChecklist, useSetSectorEtf } from "../api/hooks";
import { formatShortDate } from "../lib/format";
import { useActivePane } from "../store";
import { StrategyRulesPopover } from "./StrategyRulesPopover";
import { Spinner } from "./ui/Spinner";

const MARK = { true: { icon: "✓", cls: "text-up" }, false: { icon: "✗", cls: "text-down" }, null: { icon: "–", cls: "text-muted" } };

/** "6/7" score, green when every applicable check passes. Also used as the watchlist badge. */
export function ChecklistBadge({ score, className = "" }: { score: ChecklistScore; className?: string }) {
  return (
    <span
      className={`rounded px-1 text-[11px] tabular-nums ${score.all_pass ? "bg-up/20 text-up" : "bg-hover text-muted"} ${className}`}
      title="Chart Checklist items passed"
    >
      {score.passed}/{score.applicable}
    </span>
  );
}

/** The Chart Checklist (strategy-rules.md) for the active chart's symbol, measured. */
export function ChecklistPanel() {
  const { symbol } = useActivePane();
  const checklist = useChecklist(symbol);
  const data = checklist.data;

  return (
    <section className="max-h-[50%] shrink-0 overflow-y-auto border-t-4 border-border">
      <div className="sticky top-0 flex h-9 items-center gap-2 bg-bg px-3">
        <h2 className="font-medium">Checklist</h2>
        <StrategyRulesPopover />
        <span className="text-muted">{symbol}</span>
        <span className="flex-1" />
        {checklist.isFetching && <Spinner size={12} />}
        {data && <ChecklistBadge score={data} />}
      </div>
      {checklist.error && <p className="px-3 pb-2 text-xs text-down">{checklist.error.message}</p>}
      {data && (
        <ul className="pb-2">
          {data.checks.map((c, i) => {
            const mark = MARK[String(c.passed) as keyof typeof MARK];
            return (
              <li key={c.id} className="flex gap-2 px-3 py-1" title={`Pass when: ${c.threshold}`}>
                <span className={`w-3 shrink-0 font-semibold ${mark.cls}`}>{mark.icon}</span>
                <div className="min-w-0">
                  <div className={c.passed === null ? "text-muted" : "text-text"}>
                    {/* numbered to match the Chart Checklist in strategy-rules.md */}
                    <span className="text-muted">{i + 1}.</span> {c.label}
                  </div>
                  <div className="truncate text-xs text-muted" title={c.value}>
                    {c.value}
                  </div>
                  {c.id === "sector_etf" && data.sector_etf && symbol && (
                    <SectorEtfEditor key={symbol} symbol={symbol} current={data.sector_etf} />
                  )}
                </div>
              </li>
            );
          })}
          {data.as_of && <li className="px-3 pt-1 text-[11px] text-muted">As of {formatShortDate(data.as_of)} close</li>}
        </ul>
      )}
    </section>
  );
}

/** Row #14: change the sector ETF used for this symbol, or go back to the suggestion. */
function SectorEtfEditor({ symbol, current }: { symbol: string; current: SectorEtf }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(current.etf);
  const save = useSetSectorEtf(symbol);

  const submit = (etf: string | null) => save.mutate(etf, { onSuccess: () => setEditing(false) });
  const link = "text-[11px] text-accent hover:underline disabled:opacity-50";

  if (!editing) {
    return (
      <div className="flex gap-3">
        <button className={link} onClick={() => { setText(current.etf); setEditing(true); }}>
          ✎ change ETF
        </button>
        {current.source === "override" && current.suggested && (
          <button className={link} onClick={() => submit(null)} disabled={save.isPending}>
            use suggestion ({current.suggested})
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="mt-1">
      <div className="flex items-center gap-2">
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit(text.trim() || null);
            if (e.key === "Escape") setEditing(false);
          }}
          placeholder="ETF symbol"
          className="w-24 rounded border border-border bg-bg px-1.5 py-0.5 text-xs text-text uppercase outline-none focus:border-accent"
          aria-label="Sector ETF"
        />
        {save.isPending ? <Spinner size={12} /> : <span className="text-[11px] text-muted">Enter to save · Esc</span>}
      </div>
      {save.error && <p className="text-[11px] text-down">{save.error.message}</p>}
    </div>
  );
}
