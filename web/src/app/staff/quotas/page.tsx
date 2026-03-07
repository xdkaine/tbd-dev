"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { QuotaWithProject } from "@/lib/types";

export default function StaffQuotasPage() {
  const [quotas, setQuotas] = useState<QuotaWithProject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const limit = 25;

  const fetchQuotas = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.admin.quotas.list({
        skip: page * limit,
        limit,
        search: search || undefined,
      });
      setQuotas(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quotas");
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchQuotas();
  }, [fetchQuotas]);

  const totalPages = Math.ceil(total / limit);

  // Summary stats from current page
  const totalCpu = quotas.reduce((sum, q) => sum + q.cpu_limit, 0);
  const totalRam = quotas.reduce((sum, q) => sum + q.ram_limit, 0);
  const totalDisk = quotas.reduce((sum, q) => sum + q.disk_limit, 0);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Quotas</h1>
        <p className="text-sm text-zinc-500">
          Resource limits per project &mdash; {total} projects with quotas
        </p>
      </div>

      {/* Summary cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <SummaryCard label="Projects" value={total} />
        <SummaryCard label="Total vCPUs" value={totalCpu} sub="this page" />
        <SummaryCard
          label="Total RAM"
          value={`${(totalRam / 1024).toFixed(1)} GB`}
          sub="this page"
        />
        <SummaryCard
          label="Total Disk"
          value={`${(totalDisk / 1024).toFixed(1)} GB`}
          sub="this page"
        />
      </div>

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          aria-label="Search projects"
          className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          placeholder="Search projects..."
        />
      </div>

      {/* Table */}
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {loading ? (
        <p className="text-sm text-zinc-500">Loading quotas...</p>
      ) : quotas.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No quotas found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Project
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Owner
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-zinc-400">
                    CPU (vCPU)
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-zinc-400">
                    RAM (MB)
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-zinc-400">
                    Disk (MB)
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {quotas.map((q) => (
                  <tr key={q.id} className="hover:bg-zinc-800/50">
                    <td className="px-4 py-2">
                      <div>
                        <p className="font-medium text-zinc-100">
                          {q.project_name}
                        </p>
                        <p className="font-mono text-xs text-zinc-500">
                          {q.project_slug}
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-400">
                      {q.owner_username}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className="font-mono text-xs font-semibold text-zinc-100">
                        {q.cpu_limit}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className="font-mono text-xs text-zinc-300">
                        {q.ram_limit}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className="font-mono text-xs text-zinc-300">
                        {q.disk_limit}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-sm">
              <p className="text-xs text-zinc-500">
                Page {page + 1} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() =>
                    setPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={page >= totalPages - 1}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 disabled:opacity-50"
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

function SummaryCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: number | string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs font-medium text-zinc-500">
        {label}
        {sub && (
          <span className="ml-1 font-normal text-zinc-500">({sub})</span>
        )}
      </p>
      <p className="mt-1 text-2xl font-bold text-zinc-100">{value}</p>
    </div>
  );
}
