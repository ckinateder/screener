import { useState } from "react";
import type { IndicatorSetting } from "../api/client";
import { useResetSettings, useSaveSettings, useSettings } from "../api/hooks";
import { indicatorLabel } from "../lib/series";
import { useUi } from "../store";
import { Modal } from "./ui/Modal";

type NumField = "length" | "ema_length" | "atr_length" | "multiplier";

const FIELDS: Record<IndicatorSetting["kind"], { field: NumField; label: string; step: number; min: number; max: number }[]> = {
  ema: [{ field: "length", label: "Length", step: 1, min: 1, max: 500 }],
  kc: [
    { field: "ema_length", label: "EMA", step: 1, min: 1, max: 500 },
    { field: "atr_length", label: "ATR", step: 1, min: 1, max: 500 },
    { field: "multiplier", label: "Mult", step: 0.1, min: 0.1, max: 10 },
  ],
};

export function IndicatorSettings() {
  const setOpen = useUi((s) => s.setSettingsOpen);
  const close = () => setOpen(false);
  const settings = useSettings();
  const [draft, setDraft] = useState<IndicatorSetting[]>(() => structuredClone(settings.data ?? []));
  const save = useSaveSettings();
  const reset = useResetSettings();

  const update = (id: string, patch: Partial<IndicatorSetting>) =>
    setDraft((d) => d.map((s) => (s.id === id ? { ...s, ...patch } : s)));

  const groups: [string, IndicatorSetting[]][] = [
    ["Daily", draft.filter((s) => s.tf === "D")],
    ["Weekly", draft.filter((s) => s.tf === "W")],
  ];

  return (
    <Modal title="Indicators" onClose={close} width="max-w-2xl">
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
