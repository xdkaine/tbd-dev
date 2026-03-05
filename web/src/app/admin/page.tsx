"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import type { AdminStats } from "@/lib/types";

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.admin.stats();
      setStats(res);
    } catch {
      /* */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  if (user && user.role === "JAS_Developer") {
    return (
      <p className="text-sm text-red-600">
        You do not have permission to view this page.
      </p>
    );
  }

  const isFaculty = user?.role === "JAS-Faculty";

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Admin Console</h1>
        <p className="text-sm text-gray-500">
          Platform overview and management &mdash;{" "}
          <span className="font-medium text-brand-700">{user?.role}</span>
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Loading platform stats...</p>
      ) : stats ? (
        <>
          {/* Stats grid */}
          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total Users"
              value={stats.total_users}
              href="/admin/users"
              color="blue"
            />
            <StatCard
              label="Projects"
              value={stats.total_projects}
              color="gray"
            />
            <StatCard
              label="Active Deploys"
              value={stats.active_deploys}
              sub={`${stats.total_deploys} total`}
              color="green"
            />
            <StatCard
              label="Total Builds"
              value={stats.total_builds}
              color="gray"
            />
          </div>

          {/* Infrastructure row */}
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Infrastructure
          </h2>
          <div className="mb-8 grid gap-4 sm:grid-cols-3">
            <StatCard
              label="VLANs Allocated"
              value={stats.vlans_allocated}
              sub={`${stats.vlans_available} available`}
              href="/admin/vlans"
              color="indigo"
            />
            <StatCard
              label="Network Policies"
              value={stats.total_network_policies}
              href="/admin/network-policies"
              color="amber"
            />
            <StatCard
              label="Quotas Configured"
              value={stats.total_projects}
              sub="1 per project"
              href="/admin/quotas"
              color="rose"
            />
          </div>

          {/* Quick links */}
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Quick Actions
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <QuickLink
              href="/admin/users"
              title="User Management"
              description="View all users, manage roles and permissions"
              available={true}
            />
            <QuickLink
              href="/admin/quotas"
              title="Quota Management"
              description="View and adjust project resource limits"
              available={true}
            />
            <QuickLink
              href="/admin/network-policies"
              title="Network Policies"
              description="Manage egress/ingress firewall rules per project"
              available={isFaculty}
              badge={!isFaculty ? "Faculty only" : undefined}
            />
            <QuickLink
              href="/admin/vlans"
              title="VLAN Management"
              description="Network segmentation and VLAN allocations"
              available={true}
            />
            <QuickLink
              href="/admin/audit"
              title="Audit Log"
              description="Platform activity trail and event history"
              available={true}
            />
          </div>
        </>
      ) : (
        <p className="text-sm text-gray-500">Unable to load stats.</p>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  href,
  color = "gray",
}: {
  label: string;
  value: number;
  sub?: string;
  href?: string;
  color?: "blue" | "green" | "indigo" | "amber" | "rose" | "gray";
}) {
  const colorMap = {
    blue: "border-l-blue-500",
    green: "border-l-green-500",
    indigo: "border-l-indigo-500",
    amber: "border-l-amber-500",
    rose: "border-l-rose-500",
    gray: "border-l-gray-300",
  };

  const inner = (
    <div
      className={`rounded-lg border border-gray-200 border-l-4 ${colorMap[color]} p-4 transition-shadow hover:shadow-sm`}
    >
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );

  if (href) {
    return <Link href={href}>{inner}</Link>;
  }
  return inner;
}

function QuickLink({
  href,
  title,
  description,
  available,
  badge,
}: {
  href: string;
  title: string;
  description: string;
  available: boolean;
  badge?: string;
}) {
  if (!available) {
    return (
      <div className="relative rounded-lg border border-gray-200 bg-gray-50 p-4 opacity-60">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <p className="mt-1 text-xs text-gray-500">{description}</p>
        {badge && (
          <span className="absolute right-3 top-3 rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-medium text-gray-500">
            {badge}
          </span>
        )}
      </div>
    );
  }

  return (
    <Link
      href={href}
      className="group rounded-lg border border-gray-200 p-4 transition-all hover:border-brand-300 hover:shadow-sm"
    >
      <h3 className="text-sm font-semibold text-gray-900 group-hover:text-brand-700">
        {title}
      </h3>
      <p className="mt-1 text-xs text-gray-500">{description}</p>
    </Link>
  );
}
