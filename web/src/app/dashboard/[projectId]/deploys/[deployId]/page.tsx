"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";
import { DeployPipeline } from "@/components/deploy-pipeline";
import { useLogStream } from "@/hooks/useLogStream";
import type { Deploy, DeployStatus, Environment, Project } from "@/lib/types";

const TERMINAL_STATUSES = ["active", "failed", "rolled_back", "superseded"];

export default function DeployDetailPage() {
  const params = useParams();
  const projectId = params.projectId as string;
  const deployId = params.deployId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [deploy, setDeploy] = useState<Deploy | null>(null);
  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rolling, setRolling] = useState(false);

  const logsEndRef = useRef<HTMLPreElement>(null);

  const fetchData = useCallback(async () => {
    try {
      const [proj, deploys, envs] = await Promise.all([
        api.projects.get(projectId),
        api.deploys.list(projectId, 0, 100),
        api.environments.list(projectId),
      ]);
      setProject(proj);

      const found = deploys.items.find((d) => d.id === deployId);
      if (!found) {
        setError("Deploy not found");
        return;
      }
      setDeploy(found);

      const env = envs.items.find((e) => e.id === found.env_id);
      setEnvironment(env ?? null);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to load deploy details");
    } finally {
      setLoading(false);
    }
  }, [projectId, deployId]);

  useEffect(() => {
    fetchData();
    // Auto-refresh for in-progress deploys (metadata only)
    const interval = setInterval(() => {
      if (
        deploy &&
        !TERMINAL_STATUSES.includes(deploy.status)
      ) {
        fetchData();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchData, deploy?.status]);

  // --- SSE log streaming ---
  const isTerminal = deploy ? TERMINAL_STATUSES.includes(deploy.status) : true;

  // Only connect SSE while deploy is in progress
  const streamUrl = useMemo(() => {
    if (!deploy || isTerminal) return null;
    return api.deploys.logsStreamUrl(projectId, deployId);
  }, [deploy, isTerminal, projectId, deployId]);

  const token = typeof window !== "undefined" ? getToken() : null;
  const logStream = useLogStream(streamUrl, token);

  // For terminal deploys, fetch logs once via REST
  const [restLogs, setRestLogs] = useState<string | null>(null);
  useEffect(() => {
    if (!deploy || !isTerminal) return;
    api.deploys.logs(projectId, deployId).then((res) => {
      setRestLogs(res.logs);
    }).catch(() => {
      // ignore
    });
  }, [deploy, isTerminal, projectId, deployId]);

  const displayLogs = isTerminal ? restLogs : logStream.logs;

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollTop = logsEndRef.current.scrollHeight;
    }
  }, [displayLogs]);

  async function handleRollback() {
    if (!deploy) return;
    setRolling(true);
    try {
      await api.deploys.rollback(deploy.id, "Rolled back from deploy viewer");
      fetchData();
    } catch {
      /* */
    } finally {
      setRolling(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-gray-500">Loading deploy...</p>;
  }

  if (error || !deploy || !project) {
    return (
      <div>
        <p className="text-sm text-red-600">{error || "Deploy not found"}</p>
        <Link
          href={`/dashboard/${projectId}`}
          className="mt-2 inline-block text-sm text-brand-600"
        >
          Back to project
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div className="mb-4 text-sm">
        <Link href="/dashboard" className="text-gray-400 hover:text-gray-600">
          Projects
        </Link>
        <span className="mx-1 text-gray-300">/</span>
        <Link
          href={`/dashboard/${projectId}`}
          className="text-gray-400 hover:text-gray-600"
        >
          {project.name}
        </Link>
        <span className="mx-1 text-gray-300">/</span>
        <span className="font-medium text-gray-700">
          Deploy {deploy.id.slice(0, 8)}
        </span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            Deploy {deploy.id.slice(0, 8)}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {environment
              ? `${environment.name} (${environment.type})`
              : "Unknown environment"}
            {deploy.url && (
              <>
                {" "}
                &middot;{" "}
                <a
                  href={deploy.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-600 hover:underline"
                >
                  {deploy.url.replace("http://", "")}
                </a>
              </>
            )}
          </p>
        </div>

        {(deploy.status === "active" || deploy.status === "healthy") && (
          <button
            onClick={handleRollback}
            disabled={rolling}
            className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {rolling ? "Rolling back..." : "Rollback"}
          </button>
        )}
      </div>

      {/* State machine pipeline */}
      <div className="mb-8 rounded-lg border border-gray-200 bg-gray-50 p-6">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">
          Deploy Pipeline
        </h2>
        <DeployPipeline status={deploy.status as DeployStatus} />
      </div>

      {/* Deploy Logs */}
      <div className="mb-8 rounded-lg border border-gray-200 bg-gray-900 p-4">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-300">Deploy Logs</h2>
          {logStream.isStreaming && (
            <span className="inline-flex items-center gap-1 text-xs text-amber-400">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
              Live
            </span>
          )}
          {logStream.error && (
            <span className="text-xs text-red-400">{logStream.error}</span>
          )}
        </div>
        {displayLogs ? (
          <pre
            ref={logsEndRef}
            className="max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-green-400"
          >
            {displayLogs}
          </pre>
        ) : (
          <p className="text-sm text-gray-500">
            {!isTerminal
              ? "Waiting for deploy output..."
              : "No logs available for this deploy."}
          </p>
        )}
      </div>

      {/* Details grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <DetailCard label="Status">
          <StatusBadge status={deploy.status} />
        </DetailCard>
        <DetailCard label="Deploy ID">
          <code className="text-xs text-gray-700">{deploy.id}</code>
        </DetailCard>
        <DetailCard label="Environment">
          <span className="text-sm text-gray-900">
            {environment?.name ?? "—"} ({environment?.type ?? "—"})
          </span>
        </DetailCard>
        <DetailCard label="Artifact ID">
          <code className="text-xs text-gray-700">
            {deploy.artifact_id ?? "—"}
          </code>
        </DetailCard>
        <DetailCard label="Created">
          <span className="text-sm text-gray-700">
            {formatDate(deploy.created_at)}
          </span>
        </DetailCard>
        <DetailCard label="Promoted">
          <span className="text-sm text-gray-700">
            {deploy.promoted_at ? formatDate(deploy.promoted_at) : "—"}
          </span>
        </DetailCard>
      </div>

      {/* Auto-refresh indicator */}
      {!isTerminal && (
        <p className="mt-4 text-xs text-gray-400">
          Auto-refreshing every 5 seconds...
        </p>
      )}
    </div>
  );
}

function DetailCard({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-200 p-3">
      <p className="mb-1 text-xs font-medium text-gray-500">{label}</p>
      {children}
    </div>
  );
}
