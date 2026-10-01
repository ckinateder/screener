import type { ChartData, IndicatorSetting, Zone } from "../api/client";
import { changeClass, formatChange, formatPct, formatPrice, formatVolume } from "../lib/format";
import { appliesTo, indicatorLabel, isPriceOnly, seriesKeys, type LegendSnapshot } from "../lib/series";

interface Props {
  data: ChartData;
  settings: IndicatorSetting[];
  snapshot: LegendSnapshot;
  onToggle: (id: string) => void;
  onOpenSettings: () => void;
}

export function Legend({ data, settings, snapshot, onToggle, onOpenSettings }: Props) {
  const { bar, prevClose, values } = snapshot;
  const change = bar && prevClose != null ? bar.close - prevClose : null;
  const priceOnly = isPriceOnly(data.bars);
  // Price-only bars have open == close, so colour by the change from the previous close instead.
  const barClass = (priceOnly ? (change ?? 0) >= 0 : bar && bar.close >= bar.open) ? "text-up" : "text-down";

  return (
    <div className="pointer-events-none absolute top-2 left-3 z-10 select-none text-[13px] leading-6">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-base font-medium text-text">{data.symbol}</span>
        {data.name && <span className="text-muted">{data.name}</span>}
        <span className="text-muted">· {data.tf === "D" ? "1D" : "1W"}</span>
        {data.exchange && <span className="text-muted">· {data.exchange}</span>}
        {data.stale && <span className="text-amber-400">· offline, showing stored data</span>}
      </div>
      {bar && (
        <div className="flex flex-wrap gap-x-2">
          {/* Price-only symbols (funds): O/H/L equal the close and volume is 0, so show just C. */}
          {(priceOnly ? (["close"] as const) : (["open", "high", "low", "close"] as const)).map((f) => (
            <span key={f}>
              <span className="text-muted">{f[0].toUpperCase()}</span>{" "}
              <span className={barClass}>{formatPrice(bar[f])}</span>
            </span>
          ))}
          <span className={changeClass(change)}>
            {formatChange(change)} ({formatPct(change != null && prevClose ? (change / prevClose) * 100 : null)})
          </span>
          {!priceOnly && (
            <span>
              <span className="text-muted">Vol</span> <span className={barClass}>{formatVolume(bar.volume)}</span>
            </span>
          )}
        </div>
      )}
      {settings
        .filter((s) => appliesTo(s, data.tf))
        .map((s) => (
          <div key={s.id} className="group pointer-events-auto flex w-fit items-center gap-2 rounded px-1 -mx-1 hover:bg-pane/80">
            <span className={s.visible ? "text-text" : "text-muted line-through"}>{indicatorLabel(s)}</span>
            {s.visible &&
              seriesKeys(s).map((key) => (
                <span key={key} style={{ color: s.color }}>
                  {formatPrice(values[key])}
                </span>
              ))}
            {s.visible && s.kind === "sr" && <ZoneSummary zones={data.zones?.[s.id] ?? []} color={s.color} />}
            <span className="hidden gap-1 group-hover:flex">
              <IconButton title={s.visible ? "Hide" : "Show"} onClick={() => onToggle(s.id)}>
                {s.visible ? <EyeIcon /> : <EyeOffIcon />}
              </IconButton>
              <IconButton title="Settings" onClick={onOpenSettings}>
                <GearIcon />
              </IconButton>
            </span>
          </div>
        ))}
    </div>
  );
}

/** Support zones as "212.40 ×4 · 198.10 ×2" (centre price, touches), nearest first. */
function ZoneSummary({ zones, color }: { zones: Zone[]; color: string }) {
  if (zones.length === 0) return <span className="text-muted">none below price</span>;
  return (
    <span style={{ color }}>
      {zones.map((z) => `${formatPrice((z.low + z.high) / 2)} ×${z.touches}`).join(" · ")}
    </span>
  );
}

function IconButton({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button title={title} onClick={onClick} className="rounded p-0.5 text-muted hover:bg-hover hover:text-text">
      {children}
    </button>
  );
}

const iconProps = { width: 14, height: 14, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2 };

const EyeIcon = () => (
  <svg {...iconProps}>
    <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = () => (
  <svg {...iconProps}>
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 19c-7 0-11-7-11-7a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 5c7 0 11 7 11 7a18.5 18.5 0 0 1-2.16 3.19M1 1l22 22" />
  </svg>
);

const GearIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);
