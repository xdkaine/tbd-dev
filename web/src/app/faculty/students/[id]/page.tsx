"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { StudentDetail } from "@/lib/types";

export default function FacultyStudentDetailPage() {
  const params = useParams();
  const userId = params.id as string;

  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStudent = useCallback(async () => {
    try {
      setError(null);
      const data = await api.admin.students.get(userId);
      setStudent(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load student details",
      );
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchStudent();
  }, [fetchStudent]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-zinc-500">Loading student details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-10 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Link
          href="/faculty/students"
          className="mt-2 inline-block text-sm text-brand-400 hover:text-brand-300"
        >
          Back to Students
        </Link>
      </div>
    );
  }

  if (!student) return null;

  const healthScore =
    student.total_deploys > 0
      ? Math.round(
          ((student.total_deploys - student.failed_deploys) /
            student.total_deploys) *
            100,
        )
      : 100;

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/faculty/students"
          className="mb-3 inline-flex items-center text-sm text-zinc-500 hover:text-zinc-300"
        >
          &larr; Back to Students
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">
              {student.display_name}
            </h1>
            <p className="text-sm text-zinc-500">
              @{student.username} &middot; {student.email}
              {student.github_username && (
                <span className="ml-2 text-zinc-600">
                  GitHub: {student.github_username}
                </span>
              )}
            </p>
          </div>
          {/* Faculty action: link to user management */}
          <Link
            href={`/faculty/users`}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
          >
            Manage User
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid gap-4 sm:grid-cols-6">
        <StatCard label="Projects" value={student.projects.length} />
        <StatCard label="Total Deploys" value={student.total_deploys} />
        <StatCard label="Active Deploys" value={student.active_deploys} />
        <StatCard label="Failed Deploys" value={student.failed_deploys} accent="red" />
        <StatCard label="Total Builds" value={student.total_builds} />
        <StatCard
          label="Success Rate"
          value={`${student.success_rate.toFixed(0)}%`}
          accent={student.success_rate >= 80 ? "green" : student.success_rate >= 50 ? "yellow" : "red"}
        />
      </div>

      {/* Info row */}
      <div className="mb-6 flex flex-wrap gap-4 text-xs text-zinc-500">
        <span>
          Role:{" "}
          <span className="font-medium text-zinc-300">{student.role}</span>
        </span>
        <span>
          Joined:{" "}
          <span className="font-medium text-zinc-300">
            {formatDate(student.created_at)}
          </span>
        </span>
        {student.last_activity && (
          <span>
            Last active:{" "}
            <span className="font-medium text-zinc-300">
              {formatDate(student.last_activity)}
            </span>
          </span>
        )}
        <span>
          Health score:{" "}
          <span
            className={`font-medium ${
              healthScore >= 80
                ? "text-green-400"
                : healthScore >= 50
                  ? "text-yellow-400"
                  : "text-red-400"
            }`}
          >
            {healthScore}%
          </span>
        </span>
      </div>

      {/* Projects table */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-zinc-100">Projects</h2>
        <p className="text-sm text-zinc-500">
          {student.projects.length} project
          {student.projects.length !== 1 ? "s" : ""}
        </p>
      </div>

      {student.projects.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          This student has no projects yet.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="min-w-full divide-y divide-zinc-800 text-sm">
            <thead className="bg-zinc-900/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Project
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Framework
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Status
                </th>
                <th className="px-4 py-2 text-right font-medium text-zinc-400">
                  Deploys
                </th>
                <th className="px-4 py-2 text-right font-medium text-zinc-400">
                  Builds
                </th>
                <th className="px-4 py-2 text-right font-medium text-zinc-400">
                  Members
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Tags
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Production URL
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-400">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {student.projects.map((p) => (
                <tr key={p.id} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2">
                    <div>
                      <Link
                        href={`/dashboard/${p.id}`}
                        className="font-medium text-zinc-100 hover:text-brand-400"
                      >
                        {p.name}
                      </Link>
                      <p className="font-mono text-xs text-zinc-500">
                        {p.slug}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-400">
                    {p.framework ?? "\u2014"}
                  </td>
                  <td className="px-4 py-2">
                    <DeployStatusBadge status={p.latest_deploy_status} />
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-300">
                    {p.total_deploys}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-300">
                    {p.total_builds}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-300">
                    {p.member_count}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-1">
                      {p.tags.length > 0
                        ? p.tags.map((t) => (
                            <span
                              key={t}
                              className="inline-flex rounded-full bg-brand-950/50 px-2 py-0.5 text-[10px] font-medium text-brand-400"
                            >
                              {t}
                            </span>
                          ))
                        : <span className="text-xs text-zinc-600">\u2014</span>}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {p.production_url ? (
                      <a
                        href={p.production_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-brand-400 hover:text-brand-300"
                      >
                        {p.production_url.replace(/^https?:\/\//, "")}
                      </a>
                    ) : (
                      <span className="text-zinc-600">\u2014</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-zinc-500">
                    {formatDate(p.created_at)}
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

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: "green" | "yellow" | "red";
}) {
  const accentColors = {
    green: "text-green-400",
    yellow: "text-yellow-400",
    red: "text-red-400",
  };

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p
        className={`mt-1 text-2xl font-bold ${accent ? accentColors[accent] : "text-zinc-100"}`}
      >
        {value}
      </p>
    </div>
  );
}

function DeployStatusBadge({ status }: { status: string | null }) {
  if (!status) {
    return (
      <span className="inline-flex rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-500">
        none
      </span>
    );
  }

  const colors: Record<string, string> = {
    active: "bg-green-950/30 text-green-400",
    healthy: "bg-green-950/30 text-green-400",
    building: "bg-yellow-950/30 text-yellow-400",
    queued: "bg-yellow-950/30 text-yellow-400",
    provisioning: "bg-blue-950/30 text-blue-400",
    failed: "bg-red-950/30 text-red-400",
    stopped: "bg-zinc-800 text-zinc-500",
  };

  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] ?? "bg-zinc-800 text-zinc-400"}`}
    >
      {status}
    </span>
  );
}
