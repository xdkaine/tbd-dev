"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { StudentSummary } from "@/lib/types";

const SORT_OPTIONS = [
  { value: "created_at", label: "Joined" },
  { value: "display_name", label: "Name" },
  { value: "deploys", label: "Deploys" },
  { value: "builds", label: "Builds" },
  { value: "projects", label: "Projects" },
];

export default function FacultyStudentsPage() {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const limit = 25;

  const fetchStudents = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.admin.students.list({
        skip: page * limit,
        limit,
        search: search || undefined,
        sort: sort || undefined,
        order: order || undefined,
      });
      setStudents(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load students");
    } finally {
      setLoading(false);
    }
  }, [page, search, sort, order]);

  useEffect(() => {
    fetchStudents();
  }, [fetchStudents]);

  const totalPages = Math.ceil(total / limit);

  const totalProjects = students.reduce((s, st) => s + st.project_count, 0);
  const totalDeploys = students.reduce((s, st) => s + st.total_deploys, 0);
  const totalActive = students.reduce((s, st) => s + st.active_deploys, 0);

  return (
    <div className="max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Students</h1>
        <p className="text-sm text-zinc-500">
          Manage student activity and deployment statistics &mdash; {total} students
        </p>
      </div>

      {/* Summary cards */}
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        <SummaryCard label="Total Students" value={total} />
        <SummaryCard label="Projects" value={totalProjects} sub="this page" />
        <SummaryCard label="Deploys" value={totalDeploys} sub="this page" />
        <SummaryCard label="Active" value={totalActive} sub="running now" />
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
            placeholder="Name or username..."
          />
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
          {order === "desc" ? "Most first" : "Least first"}
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
          Loading students...
        </div>
      ) : students.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">
          No students found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Student
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Email
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Projects
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Deploys
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Builds
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-400">
                    Active
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Last Activity
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Joined
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {students.map((s) => (
                  <tr key={s.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/faculty/students/${s.id}`}
                        className="hover:text-brand-400 transition-colors"
                      >
                        <span className="font-medium text-zinc-100">{s.display_name}</span>
                        <span className="ml-1.5 text-[11px] text-zinc-600">@{s.username}</span>
                      </Link>
                      {s.github_username && (
                        <p className="text-[11px] text-zinc-600 font-mono">
                          gh: @{s.github_username}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-400">
                      {s.email}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs font-semibold text-zinc-200">
                      {s.project_count}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-zinc-300">
                      {s.total_deploys}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-zinc-300">
                      {s.total_builds}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs">
                      <span className={s.active_deploys > 0 ? "text-emerald-400 font-medium" : "text-zinc-600"}>
                        {s.active_deploys}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                      {s.last_activity ? getTimeAgo(s.last_activity) : "Never"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                      {formatDate(s.created_at)}
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
                Page {page + 1} of {totalPages} ({total} students)
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

/* ------------------------------------------------------------------ */
/*  Summary Card                                                       */
/* ------------------------------------------------------------------ */

function SummaryCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs font-medium text-zinc-500">
        {label}
        {sub && (
          <span className="ml-1 font-normal text-zinc-600">({sub})</span>
        )}
      </p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-zinc-100">
        {value.toLocaleString()}
      </p>
    </div>
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
