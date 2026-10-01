import type { ChecklistScore } from "../api/client";
import { useChecklist } from "../api/hooks";
import { formatShortDate } from "../lib/format";
import { useActivePane } from "../store";
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
                  <div className="truncate text-xs text-muted">{c.value}</div>
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
