"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import type { Vlan } from "@/lib/types";

export default function VlansPage() {
  const { user } = useAuth();
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

  // Check role — only staff/faculty
  if (user && user.role === "JAS_Developer") {
    return (
      <p className="text-sm text-red-400">
        You do not have permission to view this page.
      </p>
    );
  }

  const allocated = vlans.filter((v) => v.reserved_by_project_id);
  const available = vlans.filter((v) => !v.reserved_by_project_id);

  return (
    <div>
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

      {loading ? (
        <p className="text-sm text-zinc-500">Loading VLANs...</p>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : vlans.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No VLANs allocated yet. VLANs are auto-allocated when projects are
          created.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="min-w-full divide-y divide-zinc-800 text-sm">
            <thead className="bg-zinc-900/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  VLAN Tag
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Subnet CIDR
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Project
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {vlans.map((v) => (
                <tr key={v.id} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2 font-mono text-xs font-semibold text-zinc-100">
                    {v.vlan_tag}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-zinc-300">
                    {v.subnet_cidr}
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-300">
                    {v.reserved_by_project_id ? (
                      <code className="text-zinc-400">
                        {v.reserved_by_project_id.slice(0, 8)}...
                      </code>
                    ) : (
                      <span className="text-zinc-500">Unassigned</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {v.reserved_by_project_id ? (
                      <span className="inline-flex items-center rounded-full bg-green-950/30 px-2 py-0.5 text-xs font-medium text-green-400">
                        Allocated
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-500">
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
      <p className="mt-1 text-2xl font-bold text-zinc-100">{value}</p>
    </div>
  );
}
