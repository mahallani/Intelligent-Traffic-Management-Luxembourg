"use client";
// Reusable building blocks of the design system (2026-11-03). Styles in app/globals.css.
import Link from "next/link";
import Icon from "./icons";

export function PageHeader({ title, subtitle, actions, eyebrow }) {
  return (
    <div className="page-head">
      <div className="page-head-text">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function Card({ title, icon, actions, children, className = "", flush, subtitle, as: Tag = "section", ...rest }) {
  return (
    <Tag className={`card ${flush ? "card-flush" : ""} ${className}`} {...rest}>
      {(title || actions) && (
        <header className="card-head">
          <div className="card-title">
            {icon && <span className="card-icon"><Icon name={icon} size={18} /></span>}
            <div>
              {title && <h2>{title}</h2>}
              {subtitle && <p className="card-sub">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}

export function Kpi({ icon, label, value, unit, hint, tone = "blue", loading }) {
  return (
    <div className={`kpi-card tone-${tone}`}>
      <div className="kpi-top">
        <span className="kpi-icon"><Icon name={icon} size={18} /></span>
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-value">
        {loading ? <span className="skeleton" style={{ width: "4.5rem" }} /> : <>{value}{unit && value !== "–" && <span className="kpi-unit">{unit}</span>}</>}
      </div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

export function Badge({ tone = "neutral", children, dot, className = "" }) {
  return <span className={`badge badge-${tone} ${className}`}>{dot && <span className="badge-dot" />}{children}</span>;
}

export function Notice({ tone = "info", title, children, icon, action, role }) {
  const ic = icon || (tone === "bad" ? "alert" : tone === "warn" ? "alert" : tone === "ok" ? "check" : "info");
  return (
    <div className={`notice notice-${tone}`} role={role || (tone === "bad" ? "alert" : "status")}>
      <Icon name={ic} size={18} className="notice-icon" />
      <div className="notice-body">{title && <strong>{title} </strong>}{children}</div>
      {action}
    </div>
  );
}

export function Empty({ icon = "info", title, children, action }) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon name={icon} size={22} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Spinner({ label }) {
  return <span className="spinner-wrap" role="status"><span className="spinner" aria-hidden="true" />{label && <span>{label}</span>}</span>;
}

export function Segmented({ value, onChange, options, disabled, label, name, cols }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label} style={cols ? { display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } : undefined}>
      {options.map(([v, l, sub]) => (
        <label key={String(v)} className={`seg ${String(value) === String(v) ? "on" : ""} ${disabled ? "disabled" : ""}`}>
          <input type="radio" name={name} value={v} checked={String(value) === String(v)} disabled={disabled}
            onChange={() => onChange(v)} />
          <span>{l}</span>{sub && <small>{sub}</small>}
        </label>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange, label }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map(([id, l, count]) => (
        <button key={id} role="tab" type="button" aria-selected={value === id} onClick={() => onChange(id)}>
          {l}{count !== undefined && <span className="tab-count">{count}</span>}
        </button>
      ))}
    </div>
  );
}

export function LinkButton({ href, children, icon, variant = "secondary" }) {
  return <Link className={`btn btn-${variant}`} href={href}>{icon && <Icon name={icon} size={16} />}{children}</Link>;
}

export function Progress({ value }) {
  return <div className="progress" aria-hidden="true"><div style={{ width: `${Math.round(100 * Math.max(0, Math.min(1, value || 0)))}%` }} /></div>;
}

export function SimBadge() {
  return <Badge tone="sim">Données de simulation</Badge>;
}
