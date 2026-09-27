"""Interactive Plotly chart: daily candles + daily/weekly EMAs and Keltner Channels."""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from kaching.indicators import DAILY_EMAS, WEEKLY_EMAS, build_indicators

# Daily and weekly EMAs of the same length share a hue; weekly is dashed.
EMA_COLORS = {9: "#facc15", 21: "#22d3ee", 50: "#fb923c", 100: "#e879f9"}
KC_COLORS = {"D": "#a3e635", "W": "#94a3b8"}
KC_FILL = {"D": "rgba(163, 230, 53, 0.07)", "W": "rgba(148, 163, 184, 0.08)"}

# Traces hidden until clicked in the legend (keeps the default view readable).
HIDDEN_BY_DEFAULT = {f"W EMA {n}" for n in WEEKLY_EMAS}


def charts_dir() -> Path:
    return Path(os.environ.get("KACHING_CHARTS", "charts"))


def _visibility(name: str):
    return "legendonly" if name in HIDDEN_BY_DEFAULT else True


def _keltner_traces(ind: dict[str, pd.Series], tf: str) -> list[go.Scatter]:
    """Upper/lower/mid in one legend group so a single click toggles the whole channel."""
    label = f"Keltner {'Daily' if tf == 'D' else 'Weekly'}"
    shape = "hv" if tf == "W" else "linear"
    common = dict(legendgroup=f"kc{tf}", line=dict(color=KC_COLORS[tf], width=1, shape=shape),
                  visible=_visibility(label))
    return [
        go.Scatter(x=ind[f"{tf} KC upper"].index, y=ind[f"{tf} KC upper"], name=f"{label} upper",
                   showlegend=False, **common),
        go.Scatter(x=ind[f"{tf} KC lower"].index, y=ind[f"{tf} KC lower"], name=f"{label} lower",
                   showlegend=False, fill="tonexty", fillcolor=KC_FILL[tf], **common),
        go.Scatter(x=ind[f"{tf} KC mid"].index, y=ind[f"{tf} KC mid"], name=label,
                   **{**common, "line": dict(color=KC_COLORS[tf], width=1, dash="dot", shape=shape)}),
    ]


def build_figure(ticker: str, daily: pd.DataFrame, view_start: date | None = None) -> go.Figure:
    """Indicators use the full history (correct EMA warm-up); view_start only sets the initial x-range."""
    ind = build_indicators(daily)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=daily.index, open=daily["open"], high=daily["high"],
                                 low=daily["low"], close=daily["close"], name=ticker))
    for tf in ("D", "W"):
        for trace in _keltner_traces(ind, tf):
            fig.add_trace(trace)
    for n in DAILY_EMAS:
        name = f"D EMA {n}"
        fig.add_trace(go.Scatter(x=daily.index, y=ind[name], name=name, visible=_visibility(name),
                                 line=dict(color=EMA_COLORS[n], width=1.5)))
    for n in WEEKLY_EMAS:
        name = f"W EMA {n}"
        fig.add_trace(go.Scatter(x=daily.index, y=ind[name], name=name, visible=_visibility(name),
                                 line=dict(color=EMA_COLORS[n], width=1.5, dash="dash", shape="hv")))

    fig.update_layout(
        title=f"{ticker} — daily",
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(groupclick="togglegroup"),
        xaxis=dict(
            rangeslider=dict(visible=False),
            rangebreaks=[dict(bounds=["sat", "mon"])],
            rangeselector=dict(buttons=[
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(step="all", label="All"),
            ]),
        ),
        yaxis=dict(title="Price"),
        margin=dict(l=50, r=20, t=60, b=40),
    )
    if view_start is not None:
        visible = daily[daily.index >= pd.Timestamp(view_start)]
        if not visible.empty:
            # Plotly doesn't auto-fit y to an initial x-range, so set both explicitly.
            pad = (visible["high"].max() - visible["low"].min()) * 0.05
            fig.update_xaxes(range=[visible.index[0], visible.index[-1]])
            fig.update_yaxes(range=[visible["low"].min() - pad, visible["high"].max() + pad])
    return fig


def save_chart(fig: go.Figure, ticker: str) -> Path:
    out = charts_dir() / f"{ticker}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out, include_plotlyjs="cdn")
    return out
