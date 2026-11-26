import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";

import { apiErrorMessage, getAdminMetrics } from "../api/client";
import type { AdminMetrics } from "../api/types";
import { fadeUp } from "../lib/motion";

function formatMinutes(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 60) return `${minutes} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

export default function AdminOverviewView() {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMetrics(await getAdminMetrics());
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load the handoff metrics."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const tiles = metrics
    ? [
        {
          label: "Median time to acknowledge",
          value: formatMinutes(metrics.median_tta_minutes),
          hint: `Average ${formatMinutes(metrics.avg_tta_minutes)}`,
        },
        {
          label: "Clean-accept rate",
          value:
            metrics.clean_accept_rate === null
              ? "—"
              : `${Math.round(metrics.clean_accept_rate * 100)}%`,
          hint: `${metrics.by_status.accepted} of ${metrics.responded} answered`,
        },
        {
          label: "Awaiting response",
          value: String(metrics.by_status.pending),
          hint: `${metrics.handoffs_total} handoffs in total`,
        },
        {
          label: "Open doctor alerts",
          value: String(metrics.open_alerts),
          hint: "Not yet acknowledged",
        },
        {
          label: "Nurses on shift",
          value: String(metrics.nurses_on_shift),
          hint: `of ${metrics.nurses_active} active nurses`,
        },
      ]
    : [];

  return (
    <div className="screen-wrapper">
      <header className="screen-header">
        <div>
          <h1 className="screen-title">Overview</h1>
          <p className="screen-subtitle">How handoffs are going on the ward</p>
        </div>
      </header>

      {error && <p className="form-error mb-4">{error}</p>}

      {!metrics && !error ? (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="skeleton-row" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {tiles.map((tile, index) => (
            <motion.div
              key={tile.label}
              custom={index}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              className="handoff-card"
            >
              <p className="section-title">{tile.label}</p>
              <p className="mt-2 text-2xl font-extrabold text-[var(--text-primary)]">
                {tile.value}
              </p>
              <p className="patient-meta">{tile.hint}</p>
            </motion.div>
          ))}
        </div>
      )}

      {metrics && (
        <>
          <p className="section-title mt-6 mb-2">Responses</p>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill is-accepted">
              {metrics.by_status.accepted} accepted
            </span>
            <span className="status-pill is-declined">
              {metrics.by_status.declined} declined
            </span>
            <span className="status-pill is-issue">
              {metrics.by_status.issue_reported} issue reported
            </span>
            <span className="status-pill is-pending">
              {metrics.by_status.pending} pending
            </span>
          </div>
          <p className="patient-meta mt-4">
            Calculated from the sent and responded timestamps stored with every handoff.
          </p>
        </>
      )}
    </div>
  );
}
