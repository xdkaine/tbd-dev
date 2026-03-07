"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Vlan } from "@/lib/types";

export default function FacultyVlansPage() {
  const [vlans, setVlans] = useState<Vlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchVlans = useCallback(async () => {
    try {
      setError(null);
      const res = await api.networks.listVlans();
      setVlans(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load VLANs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVlans();
  }, [fetchVlans]);

  const allocated = vlans.filter((v) => v.reserved_by_project_id);
  const available = vlans.filter((v) => !v.reserved_by_project_id);

  return (
    <div className="max-w-7xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">VLAN Management</h1>
        <p className="text-sm text-zinc-500">
          Network segmentation: VLAN tag = 1000+N, subnet = 172.16.N.0/25
        </p>
      </div>

      {/* Summary cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Total VLANs" value={vlans.length} />
        <SummaryCard label="Allocated" value={allocated.length} />
        <SummaryCard label="Available" value={available.length} />
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
          Loading VLANs...
        </div>
      ) : vlans.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">
          No VLANs allocated yet. VLANs are auto-allocated when projects are created.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="min-w-full divide-y divide-zinc-800 text-sm">
            <thead className="bg-zinc-900/50">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                  VLAN Tag
                </th>
                <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                  Subnet CIDR
                </th>
                <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                  Project
                </th>
                <th className="px-4 py-2.5 text-left font-medium text-zinc-400">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {vlans.map((v) => (
                <tr key={v.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-semibold text-zinc-100">
                    {v.vlan_tag}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-zinc-300">
                    {v.subnet_cidr}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-zinc-300">
                    {v.reserved_by_project_id ? (
                      <code className="text-zinc-400">
                        {v.reserved_by_project_id.slice(0, 8)}...
                      </code>
                    ) : (
                      <span className="text-zinc-600">Unassigned</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {v.reserved_by_project_id ? (
                      <span className="inline-flex items-center rounded-full bg-emerald-950/30 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
                        Allocated
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-500">
                        Available
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-zinc-100">{value}</p>
    </div>
  );
}
