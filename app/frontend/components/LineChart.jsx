"use client";
// Line chart without dependency (2026-11-03; previous version: LineChart.jsx.bak_20261103).
// `x`: simulated time in seconds; `series`: [{name, values, color}]. Axes, hover read-out, empty state.
import { useEffect, useRef, useState } from "react";
import { fmt } from "./api";
import { hhmm } from "./traffic";

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

export default function LineChart({ title, unit = "", x = [], series = [], height = 150, digits = 1, area = true, legend, empty = "Pas encore de données." }) {
  const box = useRef(null);
  const [w, setW] = useState(320);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    if (!box.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, Math.round(e.contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const n = x.length;
  const vals = series.flatMap((s) => s.values || []).filter((v) => v !== null && v !== undefined);
  const max = niceMax(Math.max(0, ...vals));
  const L = 40, R = 8, T = 8, B = 22, H = height;
  const iw = Math.max(10, w - L - R), ih = H - T - B;
  const X = (i) => L + (n > 1 ? (i / (n - 1)) * iw : iw / 2);
  const Y = (v) => T + ih - (v / max) * ih;
  const path = (vs) => vs.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v ?? 0).toFixed(1)}`).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const xt = n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : [];
  const last = series[0]?.values?.length ? series[0].values[series[0].values.length - 1] : null;
  const gid = `g-${(title || "c").replace(/\W/g, "")}`;

  const onMove = (e) => {
    if (n < 2) return;
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - L) / iw) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };

  return (
    <figure className="chart-card" style={{ margin: 0 }}>
      <figcaption className="chart-head">
        <h3>{title}</h3>
        {series.length === 1 && last !== null && <span className="chart-last">{fmt(last, digits)}<small>{unit}</small></span>}
      </figcaption>
      <div className="chart-box" ref={box}>
        {n < 2 ? (
          <div className="empty" style={{ height: H, padding: "1rem" }}><p>{empty}</p></div>
        ) : (
          <svg className="chart-svg" width={w} height={H} role="img"
            aria-label={`${title} : ${series.map((s) => `${s.name} ${fmt(s.values?.[s.values.length - 1], digits)} ${unit}`).join(", ")}`}
            onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            <defs>
              {series.map((s, k) => (
                <linearGradient key={k} id={`${gid}-${k}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor={s.color || "#2478E5"} stopOpacity=".22" />
                  <stop offset="1" stopColor={s.color || "#2478E5"} stopOpacity="0" />
                </linearGradient>))}
            </defs>
            {ticks.map((t, i) => (
              <g key={i}>
                <line x1={L} x2={L + iw} y1={Y(t)} y2={Y(t)} stroke={i === 0 ? "#CBD5E1" : "#EEF2F6"} />
                <text x={L - 6} y={Y(t) + 3.5} textAnchor="end" fontSize="10.5" fill="#5B6B80">{fmt(t, t < 10 && max <= 10 ? 1 : 0)}</text>
              </g>))}
            {xt.map((i) => (
              <text key={i} x={X(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} fontSize="10.5" fill="#5B6B80">{hhmm(x[i])}</text>))}
            {series.map((s, k) => (
              <g key={s.name}>
                {area && series.length === 1 && <path d={`${path(s.values)}L${X(n - 1)},${Y(0)}L${X(0)},${Y(0)}Z`} fill={`url(#${gid}-${k})`} />}
                <path d={path(s.values)} fill="none" stroke={s.color || "#2478E5"} strokeWidth="2" strokeLinejoin="round" />
              </g>))}
            {hover !== null && (
              <g>
                <line x1={X(hover)} x2={X(hover)} y1={T} y2={T + ih} stroke="#94A3B8" strokeDasharray="3 3" />
                {series.map((s) => <circle key={s.name} cx={X(hover)} cy={Y(s.values[hover] ?? 0)} r="3.5" fill="#fff" stroke={s.color || "#2478E5"} strokeWidth="2" />)}
              </g>)}
          </svg>
        )}
        {hover !== null && n > 1 && (
          <div className="chart-tip" style={{ left: Math.min(Math.max(X(hover), 60), w - 60) }}>
            <strong>{hhmm(x[hover])}</strong>{" "}
            {series.map((s) => <span key={s.name}> · {series.length > 1 ? `${s.name} ` : ""}{fmt(s.values[hover], digits)} {unit}</span>)}
          </div>)}
      </div>
      {(legend || series.length > 1) && (
        <div className="chart-legend">{series.map((s) => <span key={s.name}><i className="lg-bar" style={{ background: s.color }} />{s.name}</span>)}</div>)}
    </figure>
  );
}
