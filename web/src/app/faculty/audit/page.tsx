"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AuditLogEntry } from "@/lib/types";

export default function FacultyAuditPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [filterAction, setFilterAction] = useState("");
  const [filterTarget, setFilterTarget] = useState("");
  const limit = 25;

  const fetchAudit = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.audit.list({
        skip: page * limit,
        limit,
        action: filterAction || undefined,
        target_type: filterTarget || undefined,
      });
      setEntries(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [page, filterAction, filterTarget]);

  useEffect(() => {
    fetchAudit();
  }, [fetchAudit]);

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="max-w-7xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Audit Log</h1>
        <p className="text-sm text-zinc-500">
          Platform activity trail &mdash; {total} total entries
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Action
          </label>
          <input
            type="text"
            value={filterAction}
            onChange={(e) => {
              setFilterAction(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            placeholder="e.g. deploy.create"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Target type
          </label>
          <input
            type="text"
            value={filterTarget}
            onChange={(e) => {
              setFilterTarget(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            placeholder="e.g. project"
          />
        </div>
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
          Loading audit log...
        </div>
      ) : entries.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">
          No audit entries found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Time
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Action
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Target
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Actor
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                    Payload
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {entries.map((e) => (
                  <tr key={e.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                      {formatDate(e.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-300">
                      {e.target_type}:{e.target_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-500">
                      {e.actor_user_id
                        ? e.actor_user_id.slice(0, 8)
                        : "system"}
                    </td>
                    <td className="max-w-[300px] truncate px-4 py-2.5 font-mono text-xs text-zinc-500">
                      {e.payload ?? "\u2014"}
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
                Page {page + 1} of {totalPages} ({total} entries)
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
