"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import { formatDate } from "@/lib/utils";
import type { AuditLogEntry } from "@/lib/types";

export default function AuditPage() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [filterAction, setFilterAction] = useState("");
  const [filterTarget, setFilterTarget] = useState("");
  const limit = 25;

  const fetchAudit = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.audit.list({
        skip: page * limit,
        limit,
        action: filterAction || undefined,
        target_type: filterTarget || undefined,
      });
      setEntries(res.items);
      setTotal(res.total);
    } catch {
      /* */
    } finally {
      setLoading(false);
    }
  }, [page, filterAction, filterTarget]);

  useEffect(() => {
    fetchAudit();
  }, [fetchAudit]);

  // Only staff/faculty
  if (user && user.role === "JAS_Developer") {
    return (
      <p className="text-sm text-red-600">
        You do not have permission to view this page.
      </p>
    );
  }

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
        <p className="text-sm text-gray-500">
          Platform activity trail — {total} total entries
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            Action
          </label>
          <input
            type="text"
            value={filterAction}
            onChange={(e) => {
              setFilterAction(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm"
            placeholder="e.g. deploy.create"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            Target type
          </label>
          <input
            type="text"
            value={filterTarget}
            onChange={(e) => {
              setFilterTarget(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm"
            placeholder="e.g. project"
          />
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-sm text-gray-500">Loading...</p>
      ) : entries.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          No audit entries found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Time
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Action
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Target
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Actor
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Payload
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {entries.map((e) => (
                  <tr key={e.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                      {formatDate(e.created_at)}
                    </td>
                    <td className="px-4 py-2">
                      <span className="inline-flex rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-700">
                      {e.target_type}:{e.target_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-500">
                      {e.actor_user_id
                        ? e.actor_user_id.slice(0, 8)
                        : "system"}
                    </td>
                    <td className="max-w-[300px] truncate px-4 py-2 font-mono text-xs text-gray-400">
                      {e.payload ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="mt-3 flex items-center justify-between text-sm">
            <p className="text-xs text-gray-500">
              Page {page + 1} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded border border-gray-300 px-3 py-1 text-xs disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() =>
                  setPage((p) => Math.min(totalPages - 1, p + 1))
                }
                disabled={page >= totalPages - 1}
                className="rounded border border-gray-300 px-3 py-1 text-xs disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
