import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";
import { dayToLogical } from "../lib/sync";

// fancy-canvas's target type, without importing that transitive dependency directly.
type RenderTarget = Parameters<IPrimitivePaneRenderer["draw"]>[0];

const MIN_HEIGHT_PX = 4; // single-touch zones have low == high; keep them visible
const FILL_ALPHA = 0.15;
const BORDER_ALPHA = 0.6;

export interface DrawZone {
  low: number;
  high: number;
  color: string; // #rrggbb
  /** First touch as fractional days since epoch (lib/sync dayNumber); the band starts there. */
  startDay: number;
  /** Shown when hovering the band. */
  tooltip: { label: string; text: string };
}

interface Rect {
  x: number;
  top: number;
  bottom: number;
}

function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/**
 * Draws support zones as translucent bands from each zone's first touch to the right edge,
 * behind the candles. Lightweight Charts has no rectangle series, hence a series primitive.
 */
export class ZonesPrimitive implements ISeriesPrimitive<Time> {
  private zones: DrawZone[] = [];
  /** Bar dates of the host chart (dayNumber), to place first-touch dates on its time scale. */
  private days: number[] = [];
  private chart: IChartApi | null = null;
  private series: ISeriesApi<"Candlestick"> | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly view: IPrimitivePaneView = {
    zOrder: () => "bottom",
    renderer: () => ({ draw: (target: RenderTarget) => this.draw(target) }),
  };

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>) {
    this.chart = chart as IChartApi;
    this.series = series as ISeriesApi<"Candlestick">;
    this.requestUpdate = requestUpdate;
  }

  detached() {
    this.chart = this.series = this.requestUpdate = null;
  }

  paneViews() {
    return [this.view];
  }

  setZones(zones: DrawZone[], days: number[]) {
    this.zones = zones;
    this.days = days;
    this.requestUpdate?.();
  }

  /** The zone under a pane point (topmost drawn wins), for hover tooltips. */
  zoneAt(x: number, y: number): DrawZone | null {
    for (let i = this.zones.length - 1; i >= 0; i--) {
      const r = this.rect(this.zones[i]);
      if (r && x >= r.x && y >= r.top && y <= r.bottom) return this.zones[i];
    }
    return null;
  }

  private rect(zone: DrawZone): Rect | null {
    if (!this.chart || !this.series) return null;
    const yHigh = this.series.priceToCoordinate(zone.high);
    const yLow = this.series.priceToCoordinate(zone.low);
    if (yHigh == null || yLow == null) return null;
    let top = Math.min(yHigh, yLow);
    let bottom = Math.max(yHigh, yLow);
    if (bottom - top < MIN_HEIGHT_PX) {
      const mid = (top + bottom) / 2;
      top = mid - MIN_HEIGHT_PX / 2;
      bottom = mid + MIN_HEIGHT_PX / 2;
    }
    const logical = dayToLogical(this.days, zone.startDay);
    const x = logical == null ? 0 : (this.chart.timeScale().logicalToCoordinate(logical as never) ?? 0);
    return { x: Math.max(0, x), top, bottom };
  }

  private draw(target: RenderTarget) {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const zone of this.zones) {
        const r = this.rect(zone);
        if (!r || r.x >= mediaSize.width) continue;
        const width = mediaSize.width - r.x;
        ctx.fillStyle = rgba(zone.color, FILL_ALPHA);
        ctx.fillRect(r.x, r.top, width, r.bottom - r.top);
        ctx.fillStyle = rgba(zone.color, BORDER_ALPHA);
        ctx.fillRect(r.x, r.top, width, 1);
        ctx.fillRect(r.x, r.bottom - 1, width, 1);
      }
    });
  }
}
