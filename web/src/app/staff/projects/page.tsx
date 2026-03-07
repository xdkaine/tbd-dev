"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AdminProjectItem } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-950/30 text-emerald-400",
  healthy: "bg-emerald-950/30 text-emerald-400",
  building: "bg-amber-950/30 text-amber-400",
  queued: "bg-zinc-800 text-zinc-400",
  failed: "bg-red-950/30 text-red-400",
  stopped: "bg-zinc-800 text-zinc-500",
};

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "name", label: "Name" },
  { value: "deploys", label: "Deploys" },
  { value: "builds", label: "Builds" },
];

export default function StaffProjectsPage() {
  const [projects, setProjects] = useState<AdminProjectItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const limit = 25;

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.admin.projects({
        skip: page * limit,
        limit,
        search: search || undefined,
        status: statusFilter || undefined,
        sort: sort || undefined,
        order: order || undefined,
      });
      setProjects(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, sort, order]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">All Projects</h1>
        <p className="text-sm text-zinc-500">
          Browse and monitor all student projects &mdash; {total} total
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Search
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            placeholder="Project name or owner..."
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="healthy">Healthy</option>
            <option value="building">Building</option>
            <option value="failed">Failed</option>
            <option value="stopped">Stopped</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Sort by
          </label>
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => setOrder((o) => (o === "desc" ? "asc" : "desc"))}
          className="rounded-lg border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200 transition-colors"
        >
          {order === "desc" ? "Newest first" : "Oldest first"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex items-center gap-3 py-12 text-sm text-zinc-500">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading projects...
        </div>
      ) : projects.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">
          No projects found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Project
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Owner
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Deploys
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Builds
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Tags
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {projects.map((p) => (
                  <tr key={p.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/dashboard/${p.id}`}
                        className="hover:text-brand-400 transition-colors"
                      >
                        <span className="font-medium text-zinc-100">{p.name}</span>
                        <span className="ml-1.5 text-xs text-zinc-600">/{p.slug}</span>
                      </Link>
                      {p.framework && (
                        <p className="text-[11px] text-zinc-600">{p.framework}</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs text-zinc-300">{p.owner_display_name}</span>
                      <span className="ml-1 text-[11px] text-zinc-600">@{p.owner_username}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      {p.latest_deploy_status ? (
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_COLORS[p.latest_deploy_status] ?? "bg-zinc-800 text-zinc-400"}`}
                        >
                          {p.latest_deploy_status}
                        </span>
                      ) : (
                        <span className="text-[11px] text-zinc-600">No deploys</span>
                      )}
                      {p.deploy_locked && (
                        <span className="ml-1.5 text-[10px] text-amber-500" title="Deploy locked">
                          locked
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-zinc-300">
                      {p.total_deploys}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-zinc-300">
                      {p.total_builds}
                    </td>
                    <td className="px-4 py-2.5">
                      {p.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {p.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400"
                            >
                              {tag}
                            </span>
                          ))}
                          {p.tags.length > 3 && (
                            <span className="text-[10px] text-zinc-600">
                              +{p.tags.length - 3}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[10px] text-zinc-700">&mdash;</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                      {formatDate(p.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between">
              <p className="text-xs text-zinc-500">
                Page {page + 1} of {totalPages} ({total} projects)
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 hover:bg-zinc-800/50 disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 hover:bg-zinc-800/50 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
