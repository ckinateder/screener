import { useState } from "react";
import type { IndicatorSetting } from "../api/client";
import { useResetSettings, useSaveSettings, useSettings } from "../api/hooks";
import { indicatorLabel } from "../lib/series";
import { useUi, type PaneIndex } from "../store";
import { Modal } from "./ui/Modal";

type NumField =
  | "length" | "ema_length" | "atr_length" | "multiplier"
  | "pivot" | "tolerance" | "lookback_years" | "max_zones" | "min_touches";

const FIELDS: Record<IndicatorSetting["kind"], { field: NumField; label: string; step: number; min: number; max: number }[]> = {
  ema: [{ field: "length", label: "Length", step: 1, min: 1, max: 500 }],
  sma: [{ field: "length", label: "Length", step: 1, min: 1, max: 500 }],
  kc: [
    { field: "ema_length", label: "EMA", step: 1, min: 1, max: 500 },
    { field: "atr_length", label: "ATR", step: 1, min: 1, max: 500 },
    { field: "multiplier", label: "Mult", step: 0.1, min: 0.1, max: 10 },
  ],
  sr: [
    { field: "pivot", label: "Pivot", step: 1, min: 1, max: 20 },
    { field: "tolerance", label: "Tol %", step: 0.1, min: 0.1, max: 10 },
    { field: "lookback_years", label: "Years", step: 1, min: 1, max: 30 },
    { field: "max_zones", label: "Zones", step: 1, min: 1, max: 10 },
    { field: "min_touches", label: "Min touches", step: 1, min: 1, max: 10 },
  ],
};

/** Indicator settings for one chart pane (each pane has its own set). */
export function IndicatorSettings({ pane }: { pane: PaneIndex }) {
  const settings = useSettings(pane);
  // Build the draft only once this pane's settings have loaded.
  return settings.data ? <SettingsForm pane={pane} initial={settings.data} /> : null;
}

function SettingsForm({ pane, initial }: { pane: PaneIndex; initial: IndicatorSetting[] }) {
  const close = useUi((s) => s.closeSettings);
  const { symbol, tf } = useUi((s) => s.panes[pane]);
  const split = useUi((s) => s.layout !== "single");
  const [draft, setDraft] = useState<IndicatorSetting[]>(() => structuredClone(initial));
  const save = useSaveSettings(pane);
  const reset = useResetSettings(pane);
  const title = split ? `Indicators · Chart ${pane + 1} (${symbol ?? "—"} ${tf === "D" ? "1D" : "1W"})` : "Indicators";

  const update = (id: string, patch: Partial<IndicatorSetting>) =>
    setDraft((d) => d.map((s) => (s.id === id ? { ...s, ...patch } : s)));

  const groups: [string, IndicatorSetting[]][] = [
    ["Daily", draft.filter((s) => s.tf === "D")],
    ["Weekly", draft.filter((s) => s.tf === "W")],
  ];

  return (
    <Modal title={title} onClose={close} width="max-w-2xl">
      <div className="overflow-y-auto px-4 py-2">
        {groups.map(([title, items]) => (
          <section key={title} className="mb-3">
            <h3 className="py-2 text-xs font-medium uppercase tracking-wide text-muted">{title}</h3>
            {items.map((s) => (
              <div key={s.id} className="flex flex-wrap items-center gap-3 rounded px-2 py-1.5 hover:bg-hover/50">
                <input
                  type="checkbox"
                  checked={s.visible}
                  onChange={(e) => update(s.id, { visible: e.target.checked })}
                  className="size-4 accent-accent"
                  title="Visible"
                />
                <span className="w-32">{indicatorLabel(s)}</span>
                <input
                  type="color"
                  value={s.color}
                  onChange={(e) => update(s.id, { color: e.target.value })}
                  className="h-6 w-8 cursor-pointer rounded border border-border bg-transparent"
                  title="Colour"
                />
                <select
                  value={s.width}
                  onChange={(e) => update(s.id, { width: Number(e.target.value) })}
                  className="rounded border border-border bg-bg px-1 py-0.5"
                  title="Line width"
                >
                  {[1, 2, 3, 4].map((w) => (
                    <option key={w} value={w}>
                      {w}px
                    </option>
                  ))}
                </select>
                {FIELDS[s.kind].map(({ field, label, step, min, max }) => (
                  <label key={field} className="flex items-center gap-1 text-muted">
                    {label}
                    <input
                      type="number"
                      value={s[field] ?? ""}
                      step={step}
                      min={min}
                      max={max}
                      onChange={(e) => update(s.id, { [field]: e.target.value === "" ? undefined : Number(e.target.value) })}
                      className="w-16 rounded border border-border bg-bg px-1.5 py-0.5 text-text outline-none focus:border-accent"
                    />
                  </label>
                ))}
              </div>
            ))}
          </section>
        ))}
      </div>

      <div className="flex items-center gap-2 border-t border-border px-4 py-3">
        <button
          onClick={() => reset.mutate(undefined, { onSuccess: (d) => setDraft(structuredClone(d)) })}
          className="rounded px-3 py-1.5 text-muted hover:bg-hover hover:text-text"
        >
          Reset to defaults
        </button>
        {(save.error || reset.error) && <span className="text-down">{(save.error ?? reset.error)!.message}</span>}
        <div className="flex-1" />
        <button onClick={close} className="rounded border border-border px-4 py-1.5 hover:bg-hover">
          Cancel
        </button>
        <button
          onClick={() => save.mutate(draft, { onSuccess: close })}
          disabled={save.isPending}
          className="rounded bg-accent px-4 py-1.5 font-medium text-white hover:bg-accent/90 disabled:opacity-60"
        >
          Save
        </button>
      </div>
    </Modal>
  );
}
