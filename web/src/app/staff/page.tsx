"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import type {
  AdminStats,
  TrendResponse,
  TrendPoint,
  ActivityEvent,
  ActivityResponse,
} from "@/lib/types";

export default function StaffOverviewPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [trends, setTrends] = useState<TrendResponse | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [s, t, a] = await Promise.all([
        api.admin.stats(),
        api.admin.trends(30),
        api.admin.activity(20),
      ]);
      setStats(s);
      setTrends(t);
      setActivity(a.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Refresh every 60 seconds
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex items-center gap-3 text-sm text-zinc-500">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading staff dashboard...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={fetchData}
          className="mt-2 text-xs text-red-400 underline hover:text-red-300"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-zinc-100">Staff Overview</h1>
          <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-blue-400 uppercase tracking-wide">
            {user?.role}
          </span>
        </div>
        <p className="mt-1 text-sm text-zinc-500">
          Monitor platform activity, student projects, and deployment health
        </p>
      </div>

      {/* Stats grid */}
      {stats && (
        <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total Users"
            value={stats.total_users}
            icon="users"
            href="/staff/students"
            color="blue"
          />
          <StatCard
            label="Projects"
            value={stats.total_projects}
            icon="folder"
            href="/staff/projects"
            color="brand"
          />
          <StatCard
            label="Active Deploys"
            value={stats.active_deploys}
            sub={`${stats.total_deploys} total`}
            icon="deploy"
            color="emerald"
          />
          <StatCard
            label="Total Builds"
            value={stats.total_builds}
            icon="build"
            color="amber"
          />
        </div>
      )}

      {/* Main content grid: Trend chart + Activity feed */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Trend chart — takes 2 columns */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
            <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
              <h2 className="text-sm font-semibold text-zinc-200">
                Platform Activity
              </h2>
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wide">
                Last 30 days
              </span>
            </div>
            <div className="p-5">
              {trends ? (
                <TrendChart points={trends.points} />
              ) : (
                <p className="py-10 text-center text-xs text-zinc-600">
                  No trend data available
                </p>
              )}
            </div>
          </div>

          {/* Infrastructure row */}
          {stats && (
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <MiniCard
                label="VLANs"
                value={`${stats.vlans_allocated} / ${stats.vlans_allocated + stats.vlans_available}`}
                sub="allocated"
                href="/admin/vlans"
              />
              <MiniCard
                label="Network Policies"
                value={stats.total_network_policies}
                sub="active rules"
              />
              <MiniCard
                label="Quotas"
                value={stats.total_projects}
                sub="configured"
                href="/admin/quotas"
              />
            </div>
          )}
        </div>

        {/* Activity feed — 1 column */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
            <h2 className="text-sm font-semibold text-zinc-200">
              Recent Activity
            </h2>
            <Link
              href="/admin/audit"
              className="text-[10px] font-medium text-zinc-500 uppercase tracking-wide hover:text-brand-400 transition-colors"
            >
              View all
            </Link>
          </div>
          <div className="max-h-[480px] overflow-y-auto">
            {activity.length > 0 ? (
              <div className="divide-y divide-zinc-800/50">
                {activity.map((event) => (
                  <ActivityRow key={event.id} event={event} />
                ))}
              </div>
            ) : (
              <p className="py-10 text-center text-xs text-zinc-600">
                No recent activity
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Quick navigation */}
      <div className="mt-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-600">
          Quick Navigation
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickLink
            href="/staff/projects"
            title="All Projects"
            description="Browse and monitor all student projects"
          />
          <QuickLink
            href="/staff/students"
            title="Students"
            description="View student activity and deployment stats"
          />
          <QuickLink
            href="/staff/tags"
            title="Tags"
            description="Organize projects with labels"
          />
          <QuickLink
            href="/admin/audit"
            title="Audit Log"
            description="Full platform event history"
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Stat Card                                                          */
/* ------------------------------------------------------------------ */

function StatCard({
  label,
  value,
  sub,
  icon,
  href,
  color = "brand",
}: {
  label: string;
  value: number;
  sub?: string;
  icon: string;
  href?: string;
  color?: "blue" | "brand" | "emerald" | "amber" | "rose";
}) {
  const colorMap = {
    blue: { border: "border-l-blue-500", text: "text-blue-400", bg: "bg-blue-500/10" },
    brand: { border: "border-l-brand-500", text: "text-brand-400", bg: "bg-brand-500/10" },
    emerald: { border: "border-l-emerald-500", text: "text-emerald-400", bg: "bg-emerald-500/10" },
    amber: { border: "border-l-amber-500", text: "text-amber-400", bg: "bg-amber-500/10" },
    rose: { border: "border-l-rose-500", text: "text-rose-400", bg: "bg-rose-500/10" },
  };

  const c = colorMap[color];
  const iconMap: Record<string, JSX.Element> = {
    users: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-1.053M18 6.75a3 3 0 11-6 0 3 3 0 016 0zm-8.25 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
      </svg>
    ),
    folder: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
      </svg>
    ),
    deploy: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 8.689c0-.864.933-1.406 1.683-.977l7.108 4.061a1.125 1.125 0 010 1.954l-7.108 4.061A1.125 1.125 0 013 16.811V8.69zM12.75 8.689c0-.864.933-1.406 1.683-.977l7.108 4.061a1.125 1.125 0 010 1.954l-7.108 4.061a1.125 1.125 0 01-1.683-.977V8.69z" />
      </svg>
    ),
    build: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17l-5.1-5.1m0 0L11.42 4.97m-5.1 5.1H21M3 3v18" />
      </svg>
    ),
  };

  const inner = (
    <div className={`rounded-lg border border-zinc-800 border-l-4 ${c.border} bg-zinc-900/50 p-4 transition-all hover:bg-zinc-900/80`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-zinc-500">{label}</p>
        <div className={`rounded-md p-1.5 ${c.bg}`}>
          <span className={c.text}>{iconMap[icon]}</span>
        </div>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums text-zinc-100">
        {value.toLocaleString()}
      </p>
      {sub && <p className="mt-0.5 text-[11px] text-zinc-500">{sub}</p>}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block">
        {inner}
      </Link>
    );
  }
  return inner;
}

/* ------------------------------------------------------------------ */
/*  Trend Chart (CSS-based bar chart)                                  */
/* ------------------------------------------------------------------ */

function TrendChart({ points }: { points: TrendPoint[] }) {
  const maxVal = Math.max(
    ...points.map((p) => Math.max(p.deploys + p.builds, 1)),
    1,
  );

  // Show last 30 days, aggregate to show clearly
  const displayPoints = points.slice(-30);

  return (
    <div>
      {/* Legend */}
      <div className="mb-4 flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <div className="h-2.5 w-2.5 rounded-sm bg-brand-500" />
          <span className="text-[11px] text-zinc-500">Deploys</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-2.5 w-2.5 rounded-sm bg-blue-500" />
          <span className="text-[11px] text-zinc-500">Builds</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-2.5 w-2.5 rounded-sm bg-red-500/60" />
          <span className="text-[11px] text-zinc-500">Failed</span>
        </div>
      </div>

      {/* Bars */}
      <div className="flex items-end gap-[3px]" style={{ height: "160px" }}>
        {displayPoints.map((point, i) => {
          const deployH = (point.deploys / maxVal) * 100;
          const buildH = (point.builds / maxVal) * 100;
          const failedH =
            ((point.failed_deploys + point.failed_builds) / maxVal) * 100;
          const isToday = i === displayPoints.length - 1;
          const dayLabel = new Date(point.date + "T00:00:00").toLocaleDateString(
            "en-US",
            { month: "short", day: "numeric" },
          );

          return (
            <div
              key={point.date}
              className="group relative flex flex-1 flex-col items-center justify-end"
              style={{ height: "100%" }}
            >
              {/* Tooltip */}
              <div className="pointer-events-none absolute -top-14 left-1/2 z-10 hidden -translate-x-1/2 rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 shadow-lg group-hover:block">
                <p className="whitespace-nowrap text-[10px] font-medium text-zinc-300">
                  {dayLabel}
                </p>
                <p className="whitespace-nowrap text-[10px] text-zinc-400">
                  {point.deploys}d / {point.builds}b
                  {point.failed_deploys + point.failed_builds > 0
                    ? ` / ${point.failed_deploys + point.failed_builds}f`
                    : ""}
                </p>
              </div>

              {/* Stacked bars */}
              <div className="flex w-full flex-col items-center gap-[1px]">
                {failedH > 0 && (
                  <div
                    className="w-full rounded-t-[2px] bg-red-500/50"
                    style={{ height: `${Math.max(failedH, 2)}%` }}
                  />
                )}
                {buildH > 0 && (
                  <div
                    className="w-full bg-blue-500/70"
                    style={{ height: `${Math.max(buildH, 2)}%` }}
                  />
                )}
                {deployH > 0 && (
                  <div
                    className={`w-full rounded-b-[2px] ${isToday ? "bg-brand-400" : "bg-brand-500/70"}`}
                    style={{ height: `${Math.max(deployH, 2)}%` }}
                  />
                )}
                {deployH === 0 && buildH === 0 && (
                  <div className="w-full rounded-[2px] bg-zinc-800/50" style={{ height: "2px" }} />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* X-axis labels */}
      <div className="mt-2 flex justify-between">
        <span className="text-[10px] text-zinc-600">
          {displayPoints.length > 0
            ? new Date(displayPoints[0].date + "T00:00:00").toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })
            : ""}
        </span>
        <span className="text-[10px] text-zinc-600">Today</span>
      </div>

      {/* Summary stats below chart */}
      <div className="mt-4 grid grid-cols-3 gap-4 border-t border-zinc-800/50 pt-4">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-600">
            Total Deploys
          </p>
          <p className="mt-0.5 text-lg font-bold tabular-nums text-zinc-200">
            {points.reduce((s, p) => s + p.deploys, 0)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-600">
            Total Builds
          </p>
          <p className="mt-0.5 text-lg font-bold tabular-nums text-zinc-200">
            {points.reduce((s, p) => s + p.builds, 0)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-600">
            Failure Rate
          </p>
          <p className="mt-0.5 text-lg font-bold tabular-nums text-zinc-200">
            {(() => {
              const totalOps = points.reduce(
                (s, p) => s + p.deploys + p.builds,
                0,
              );
              const totalFailed = points.reduce(
                (s, p) => s + p.failed_deploys + p.failed_builds,
                0,
              );
              if (totalOps === 0) return "0%";
              return `${((totalFailed / totalOps) * 100).toFixed(1)}%`;
            })()}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Activity Feed Row                                                  */
/* ------------------------------------------------------------------ */

function ActivityRow({ event }: { event: ActivityEvent }) {
  const typeConfig: Record<string, { label: string; color: string; dotColor: string }> = {
    deploy: { label: "Deploy", color: "text-brand-400", dotColor: "bg-brand-400" },
    build: { label: "Build", color: "text-blue-400", dotColor: "bg-blue-400" },
    "project.create": { label: "New Project", color: "text-emerald-400", dotColor: "bg-emerald-400" },
    "project.delete": { label: "Deleted", color: "text-red-400", dotColor: "bg-red-400" },
    "user.role.update": { label: "Role Change", color: "text-amber-400", dotColor: "bg-amber-400" },
  };

  const config = typeConfig[event.type] || {
    label: event.type,
    color: "text-zinc-400",
    dotColor: "bg-zinc-500",
  };

  const statusColors: Record<string, string> = {
    active: "text-emerald-400",
    healthy: "text-emerald-400",
    success: "text-emerald-400",
    building: "text-amber-400",
    queued: "text-zinc-400",
    failed: "text-red-400",
    stopped: "text-zinc-500",
  };

  const timeAgo = getTimeAgo(event.timestamp);

  return (
    <div className="flex gap-3 px-4 py-3 transition-colors hover:bg-zinc-800/30">
      <div className="mt-1.5 flex-shrink-0">
        <div className={`h-2 w-2 rounded-full ${config.dotColor}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className={`text-xs font-medium ${config.color}`}>
            {config.label}
          </span>
          <span className="flex-shrink-0 text-[10px] text-zinc-600">
            {timeAgo}
          </span>
        </div>
        {event.project_name && (
          <p className="mt-0.5 truncate text-xs text-zinc-300">
            {event.project_id ? (
              <Link
                href={`/dashboard/${event.project_id}`}
                className="hover:text-brand-400 transition-colors"
              >
                {event.project_name}
              </Link>
            ) : (
              event.project_name
            )}
          </p>
        )}
        <div className="mt-0.5 flex items-center gap-2">
          {event.actor_username && (
            <span className="text-[11px] text-zinc-500">
              {event.actor_name || event.actor_username}
            </span>
          )}
          {event.status && (
            <span
              className={`text-[10px] font-medium ${statusColors[event.status] || "text-zinc-500"}`}
            >
              {event.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Mini infrastructure card                                           */
/* ------------------------------------------------------------------ */

function MiniCard({
  label,
  value,
  sub,
  href,
}: {
  label: string;
  value: string | number;
  sub: string;
  href?: string;
}) {
  const inner = (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-all hover:bg-zinc-900/80">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-bold tabular-nums text-zinc-200">
        {value}
      </p>
      <p className="text-[10px] text-zinc-600">{sub}</p>
    </div>
  );

  if (href) {
    return <Link href={href}>{inner}</Link>;
  }
  return inner;
}

/* ------------------------------------------------------------------ */
/*  Quick link card                                                    */
/* ------------------------------------------------------------------ */

function QuickLink({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-all hover:border-brand-500/30 hover:bg-zinc-900/80"
    >
      <h3 className="text-sm font-semibold text-zinc-200 group-hover:text-brand-400 transition-colors">
        {title}
      </h3>
      <p className="mt-1 text-xs text-zinc-500">{description}</p>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Time ago helper                                                    */
/* ------------------------------------------------------------------ */

function getTimeAgo(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = now - then;

  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;

  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
