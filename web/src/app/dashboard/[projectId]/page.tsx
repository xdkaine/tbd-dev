"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";
import { ConfirmModal } from "@/components/modal";
import { useAuth } from "@/contexts/auth";
import { useLogStream } from "@/hooks/useLogStream";
import type {
  Build,
  BuildLogsResponse,
  Deploy,
  DeployLogsResponse,
  Environment,
  GitHubRepo,
  Project,
  ProjectMember,
  UserSearchResult,
} from "@/lib/types";

type Tab = "overview" | "deploys" | "builds" | "environments" | "members" | "settings" | "secrets";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const projectId = params.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [builds, setBuilds] = useState<Build[]>([]);
  const [deploys, setDeploys] = useState<Deploy[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchAll = useCallback(async () => {
    try {
      const [proj, envs, blds, deps] = await Promise.all([
        api.projects.get(projectId),
        api.environments.list(projectId),
        api.builds.list(projectId),
        api.deploys.list(projectId),
      ]);
      setProject(proj);
      setEnvironments(envs.items);
      setBuilds(blds.items);
      setDeploys(deps.items);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Project not found");
      } else {
        setError("Failed to load project");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading...</p>;
  }

  if (error || !project) {
    return (
      <div>
        <p className="text-sm text-red-400">{error || "Project not found"}</p>
        <Link
          href="/dashboard"
          className="mt-2 inline-block text-sm text-brand-600 hover:text-brand-700"
        >
          Back to projects
        </Link>
      </div>
    );
  }

  // Derive production URL — prefer the project-level persistent URL, fall back to deploy URL
  const prodEnv = environments.find((e) => e.type === "production");
  const latestActiveDeploy = deploys.find(
    (d) =>
      (d.status === "active" || d.status === "healthy") &&
      (prodEnv ? d.env_id === prodEnv.id : true),
  );
  const productionUrl = project.production_url ?? latestActiveDeploy?.url ?? null;

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    { key: "deploys", label: "Deployments", count: deploys.length },
    { key: "builds", label: "Builds", count: builds.length },
    { key: "environments", label: "Environments", count: environments.length },
    { key: "members", label: "Members" },
    { key: "settings", label: "Settings" },
    { key: "secrets", label: "Secrets" },
  ];

  return (
    <div>
      {/* Breadcrumb */}
      <div className="mb-6">
        <div className="flex items-center gap-1.5 text-sm text-zinc-500">
          <Link href="/dashboard" className="hover:text-zinc-300 transition-colors">
            Projects
          </Link>
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
          <span className="font-medium text-zinc-300">{project.name}</span>
        </div>
      </div>

      {/* Project header — Vercel-style */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            {/* Project icon */}
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-800 bg-gradient-to-br from-zinc-900/50 to-zinc-800">
              {project.framework ? (
                <span className="text-lg font-bold text-zinc-400">
                  {project.framework.charAt(0).toUpperCase()}
                </span>
              ) : (
                <svg className="h-6 w-6 text-zinc-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                </svg>
              )}
            </div>
            <div>
              <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">{project.name}</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-zinc-500">
                {project.repo?.repo_full_name && (
                  <a
                    href={`https://github.com/${project.repo.repo_full_name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                    </svg>
                    {project.repo.repo_full_name}
                  </a>
                )}
                {project.repo?.repo_full_name && project.framework && (
                  <span className="text-zinc-600">|</span>
                )}
                {project.framework && (
                  <span className="inline-flex items-center rounded-md bg-brand-950/50 px-2 py-0.5 text-xs font-medium text-brand-400 ring-1 ring-inset ring-brand-800">
                    {project.framework}
                  </span>
                )}
                {project.repo?.default_branch && (
                  <>
                    <span className="text-zinc-600">|</span>
                    <span className="inline-flex items-center gap-1 text-xs text-zinc-500">
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.86-2.556a4.5 4.5 0 00-1.242-7.244l4.5-4.5a4.5 4.5 0 016.364 6.364L17.7 8.188" />
                      </svg>
                      {project.repo.default_branch}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Visit + actions */}
          <div className="flex items-center gap-2">
            {productionUrl && (
              <a
                href={productionUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-200 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-300 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                </svg>
                Visit
              </a>
            )}
            {project.repo?.repo_full_name && (
              <a
                href={`https://github.com/${project.repo.repo_full_name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800/50 transition-colors"
              >
                <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                </svg>
                Git
              </a>
            )}
          </div>
        </div>

      {/* Production URL display */}
      {productionUrl && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
          <a
            href={productionUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-zinc-300 hover:text-brand-600 transition-colors"
          >
            {productionUrl.replace(/^https?:\/\//, "")}
          </a>
          {project.production_url && latestActiveDeploy?.url && project.production_url !== latestActiveDeploy.url && (
              <>
              <span className="text-zinc-600">|</span>
              <a
                href={latestActiveDeploy.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-zinc-500 hover:text-brand-600 transition-colors"
                title="Immutable deploy URL"
              >
                {latestActiveDeploy.url.replace(/^https?:\/\//, "")}
              </a>
            </>
          )}
        </div>
      )}

        {/* Repo connection banner */}
        {!project.repo && (
          <RepoConnectionBanner
            projectId={projectId}
            onConnected={fetchAll}
          />
        )}
      </div>

      {/* Tab navigation */}
      <div className="mb-6 border-b border-zinc-800">
        <nav className="-mb-px flex space-x-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`relative whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
                tab === t.key
                  ? "text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className={`ml-1.5 rounded-full px-2 py-0.5 text-xs ${
                  tab === t.key
                    ? "bg-brand-950/50 text-brand-400"
                    : "bg-zinc-800 text-zinc-500"
                }`}>
                  {t.count}
                </span>
              )}
              {tab === t.key && (
                <span className="absolute inset-x-0 -bottom-px h-0.5 bg-zinc-100 rounded-full" />
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {tab === "overview" && (
        <OverviewTab
          project={project}
          deploys={deploys}
          builds={builds}
          environments={environments}
          projectId={projectId}
          onNavigate={setTab}
        />
      )}
      {tab === "deploys" && (
        <DeploysTab
          deploys={deploys}
          environments={environments}
          projectId={projectId}
          project={project}
          onUpdate={fetchAll}
        />
      )}
      {tab === "builds" && (
        <BuildsTab
          builds={builds}
          project={project}
          projectId={projectId}
          onUpdate={fetchAll}
        />
      )}
      {tab === "environments" && (
        <EnvironmentsTab
          environments={environments}
          projectId={projectId}
          onUpdate={fetchAll}
        />
      )}
      {tab === "members" && (
        <MembersTab
          project={project}
          projectId={projectId}
        />
      )}
      {tab === "settings" && (
        <SettingsTab
          project={project}
          projectId={projectId}
          onUpdate={fetchAll}
        />
      )}
      {tab === "secrets" && (
        <SecretsTabLink projectId={projectId} />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Overview tab                                                           */
/* ---------------------------------------------------------------------- */

/** Compute stats from builds and deploys data. */
function useProjectStats(builds: Build[], deploys: Deploy[]) {
  const totalDeploys = deploys.length;
  const totalBuilds = builds.length;

  const successfulBuilds = builds.filter(
    (b) => b.status === "success" || b.status === "active" || b.status === "healthy" || b.status === "artifact_ready",
  ).length;
  const successRate =
    totalBuilds > 0 ? Math.round((successfulBuilds / totalBuilds) * 100) : 0;

  const completedBuilds = builds.filter((b) => b.started_at && b.finished_at);
  const avgBuildTimeMs =
    completedBuilds.length > 0
      ? completedBuilds.reduce((sum, b) => {
          return (
            sum +
            (new Date(b.finished_at!).getTime() -
              new Date(b.started_at!).getTime())
          );
        }, 0) / completedBuilds.length
      : 0;

  const avgBuildTime = formatDurationMs(avgBuildTimeMs);

  const failedDeploys = deploys.filter((d) => d.status === "failed").length;

  return { totalDeploys, totalBuilds, successRate, avgBuildTime, failedDeploys };
}

/** Format milliseconds to a human-readable duration. */
function formatDurationMs(ms: number): string {
  if (ms <= 0) return "—";
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return `${mins}m ${rem}s`;
}

/** Generate activity data for the last N days. */
function getActivityData(deploys: Deploy[], days: number = 14) {
  const now = new Date();
  const buckets: { label: string; count: number; date: string }[] = [];

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const dayLabel = d.toLocaleDateString("en-US", { weekday: "short" });
    const dateLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    buckets.push({
      label: i < 7 ? dayLabel : dateLabel,
      count: 0,
      date: dateStr,
    });
  }

  for (const deploy of deploys) {
    const deployDate = deploy.created_at.slice(0, 10);
    const bucket = buckets.find((b) => b.date === deployDate);
    if (bucket) bucket.count++;
  }

  return buckets;
}

function OverviewTab({
  project,
  deploys,
  builds,
  environments,
  projectId,
  onNavigate,
}: {
  project: Project;
  deploys: Deploy[];
  builds: Build[];
  environments: Environment[];
  projectId: string;
  onNavigate: (tab: Tab) => void;
}) {
  const stats = useProjectStats(builds, deploys);
  const activityData = getActivityData(deploys);
  const maxActivity = Math.max(...activityData.map((d) => d.count), 1);

  const envMap = Object.fromEntries(environments.map((e) => [e.id, e]));

  // Find latest production deployment
  const prodEnv = environments.find((e) => e.type === "production");
  const latestProdDeploy = deploys.find(
    (d) => prodEnv && d.env_id === prodEnv.id,
  );
  const latestActiveDeploy = deploys.find(
    (d) => d.status === "active" || d.status === "healthy",
  );
  const featuredDeploy = latestProdDeploy ?? latestActiveDeploy ?? deploys[0];

  const recentDeploys = deploys.slice(0, 5);
  const recentBuilds = builds.slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Production deployment card */}
      {featuredDeploy ? (
        <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
          <div className="border-b border-zinc-800 bg-zinc-900/50 px-6 py-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100">
                {prodEnv ? "Production Deployment" : "Latest Deployment"}
              </h3>
              <Link
                href={`/dashboard/${projectId}/deploys/${featuredDeploy.id}`}
                className="text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
              >
                View Details
              </Link>
            </div>
          </div>
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                  featuredDeploy.status === "active" || featuredDeploy.status === "healthy"
                    ? "bg-green-950/30"
                    : featuredDeploy.status === "failed"
                      ? "bg-red-950/30"
                      : featuredDeploy.status === "stopped"
                        ? "bg-amber-950/30"
                        : "bg-zinc-900/50"
                }`}>
                  {featuredDeploy.status === "active" || featuredDeploy.status === "healthy" ? (
                    <svg className="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  ) : featuredDeploy.status === "failed" ? (
                    <svg className="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                  ) : featuredDeploy.status === "stopped" ? (
                    <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25v13.5m-7.5-13.5v13.5" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5 text-zinc-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={featuredDeploy.status} />
                    <span className="text-xs text-zinc-500">
                      {envMap[featuredDeploy.env_id]?.name ?? "Unknown"}
                    </span>
                  </div>
                  {featuredDeploy.url ? (
                    <a
                      href={featuredDeploy.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 block text-sm font-medium text-zinc-300 hover:text-brand-600 transition-colors"
                    >
                      {featuredDeploy.url.replace(/^https?:\/\//, "")}
                    </a>
                  ) : (
                    <p className="mt-1 text-sm text-zinc-500">No URL assigned</p>
                  )}
                  {project.production_url && featuredDeploy.url !== project.production_url && (
                    <a
                      href={project.production_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs text-green-400 hover:text-green-300 transition-colors"
                      title="Persistent production URL"
                    >
                      {project.production_url.replace(/^https?:\/\//, "")}
                    </a>
                  )}
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-zinc-500">{timeAgo(featuredDeploy.created_at)}</p>
                <p className="mt-0.5 text-xs text-zinc-500">{formatDate(featuredDeploy.created_at)}</p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-900/50 p-8 text-center">
          <svg className="mx-auto h-8 w-8 text-zinc-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 006.16-12.12A14.98 14.98 0 009.631 8.41m5.96 5.96a14.926 14.926 0 01-5.841 2.58m-.119-8.54a6 6 0 00-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 00-2.58 5.841m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 01-2.448-2.448 14.9 14.9 0 01.06-.312m-2.24 2.39a4.493 4.493 0 00-1.757 4.306 4.493 4.493 0 004.306-1.758M16.5 9a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z" />
          </svg>
          <p className="mt-3 text-sm font-medium text-zinc-400">No deployments yet</p>
          <p className="mt-1 text-xs text-zinc-500">Push to your connected repository to trigger the first deployment.</p>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <button
          onClick={() => onNavigate("deploys")}
          className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-left hover:border-zinc-700 hover:bg-zinc-800/50 transition-all"
        >
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Total Deploys</p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">{stats.totalDeploys}</p>
          {stats.failedDeploys > 0 && (
            <p className="mt-1 text-xs text-red-500">{stats.failedDeploys} failed</p>
          )}
        </button>
        <button
          onClick={() => onNavigate("builds")}
          className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-left hover:border-zinc-700 hover:bg-zinc-800/50 transition-all"
        >
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Total Builds</p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">{stats.totalBuilds}</p>
        </button>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Success Rate</p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">
            {stats.totalBuilds > 0 ? `${stats.successRate}%` : "—"}
          </p>
          {stats.totalBuilds > 0 && (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
              <div
                className={`h-full rounded-full transition-all ${
                  stats.successRate >= 80
                    ? "bg-green-500"
                    : stats.successRate >= 50
                      ? "bg-yellow-500"
                      : "bg-red-500"
                }`}
                style={{ width: `${stats.successRate}%` }}
              />
            </div>
          )}
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Avg Build Time</p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">{stats.avgBuildTime}</p>
        </div>
      </div>

      {/* Two-column: Activity chart + Recent activity */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Deploy activity chart */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <h3 className="mb-4 text-sm font-semibold text-zinc-100">Deploy Activity</h3>
          <div className="flex items-end gap-1" style={{ height: "120px" }}>
            {activityData.map((d, i) => (
              <div key={i} className="group relative flex flex-1 flex-col items-center justify-end h-full">
                <div
                  className={`w-full rounded-t transition-all ${
                    d.count > 0
                      ? "bg-brand-500 group-hover:bg-brand-600"
                      : "bg-zinc-800"
                  }`}
                  style={{
                    height: d.count > 0 ? `${Math.max((d.count / maxActivity) * 100, 8)}%` : "4px",
                    minHeight: d.count > 0 ? "8px" : "4px",
                  }}
                />
                {/* Tooltip */}
                <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="whitespace-nowrap rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-200 shadow-lg">
                    {d.count} deploy{d.count !== 1 ? "s" : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-zinc-500">
            <span>{activityData[0]?.label}</span>
            <span>Today</span>
          </div>
        </div>

        {/* Recent activity feed */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-100">Recent Activity</h3>
            <button
              onClick={() => onNavigate("deploys")}
              className="text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              View all
            </button>
          </div>
          {recentDeploys.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-500">No recent activity</p>
          ) : (
            <div className="space-y-3">
              {recentDeploys.map((d) => (
                <Link
                  key={d.id}
                  href={`/dashboard/${projectId}/deploys/${d.id}`}
                  className="flex items-center gap-3 rounded-lg p-2 -mx-2 hover:bg-zinc-800/50 transition-colors"
                >
                  <div className={`h-2 w-2 rounded-full shrink-0 ${
                    d.status === "active" || d.status === "healthy"
                      ? "bg-green-500"
                      : d.status === "failed"
                        ? "bg-red-500"
                        : d.status === "building" || d.status === "provisioning"
                          ? "bg-yellow-500"
                          : d.status === "stopped"
                            ? "bg-amber-500"
                            : "bg-zinc-600"
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-zinc-100 truncate">
                        {envMap[d.env_id]?.name ?? "Deploy"}
                      </span>
                      <StatusBadge status={d.status} />
                    </div>
                    {d.url && (
                      <p className="text-xs text-zinc-500 truncate">
                        {d.url.replace(/^https?:\/\//, "")}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-zinc-500 shrink-0">
                    {timeAgo(d.created_at)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent builds */}
      {recentBuilds.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
            <h3 className="text-sm font-semibold text-zinc-100">Recent Builds</h3>
            <button
              onClick={() => onNavigate("builds")}
              className="text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              View all
            </button>
          </div>
          <div className="divide-y divide-zinc-800/50">
            {recentBuilds.map((b) => (
              <div key={b.id} className="flex items-center gap-4 px-5 py-3 hover:bg-zinc-800/50 transition-colors">
                <StatusBadge status={b.status} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-zinc-300">
                      {b.commit_sha.slice(0, 8)}
                    </span>
                    {b.branch && (
                      <span className="inline-flex items-center gap-1 rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">
                        <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.86-2.556a4.5 4.5 0 00-1.242-7.244l4.5-4.5a4.5 4.5 0 016.364 6.364L17.7 8.188" />
                        </svg>
                        {b.branch}
                      </span>
                    )}
                    {b.trigger && (
                      <span className={`rounded px-1.5 py-0.5 text-xs ${
                        b.trigger === "push"
                          ? "bg-blue-950/30 text-blue-400"
                          : b.trigger === "pull_request"
                            ? "bg-purple-950/30 text-purple-400"
                            : "bg-zinc-900/50 text-zinc-400"
                      }`}>
                        {b.trigger === "pull_request" ? "PR" : b.trigger}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs text-zinc-500">{b.started_at ? timeAgo(b.started_at) : "—"}</p>
                  {b.started_at && b.finished_at && (
                    <p className="text-xs text-zinc-500">{formatDuration(b.started_at, b.finished_at)}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Environments summary */}
      {environments.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
            <h3 className="text-sm font-semibold text-zinc-100">Environments</h3>
            <button
              onClick={() => onNavigate("environments")}
              className="text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              Manage
            </button>
          </div>
          <div className="grid gap-px bg-zinc-800 sm:grid-cols-3">
            {environments.map((env) => {
              const envDeploys = deploys.filter((d) => d.env_id === env.id);
              const activeDeploy = envDeploys.find(
                (d) => d.status === "active" || d.status === "healthy",
              );
              return (
                <div key={env.id} className="bg-zinc-900/50 p-4">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${
                      activeDeploy ? "bg-green-500" : "bg-zinc-600"
                    }`} />
                    <span className="text-sm font-medium text-zinc-100">{env.name}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                      env.type === "production"
                        ? "bg-green-950/30 text-green-400"
                        : env.type === "staging"
                          ? "bg-amber-950/30 text-amber-400"
                          : "bg-zinc-800 text-zinc-400"
                    }`}>
                      {env.type}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">
                    {envDeploys.length} deploy{envDeploys.length !== 1 ? "s" : ""}
                    {activeDeploy?.url && (
                      <>
                        {" "}&middot;{" "}
                        <a
                          href={activeDeploy.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-500 hover:text-brand-600"
                        >
                          {activeDeploy.url.replace(/^https?:\/\//, "")}
                        </a>
                      </>
                    )}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Repo connection banner                                                  */
/* ---------------------------------------------------------------------- */

function RepoConnectionBanner({
  projectId,
  onConnected,
}: {
  projectId: string;
  onConnected: () => void;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  async function loadRepos() {
    setLoadingRepos(true);
    setError("");
    try {
      const data = await api.github.listRepos();
      setRepos(data);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to load GitHub repos");
    } finally {
      setLoadingRepos(false);
    }
  }

  function handleOpen() {
    setShowPicker(true);
    loadRepos();
  }

  async function handleConnect(repo: GitHubRepo) {
    setConnecting(true);
    setError("");
    try {
      await api.projects.connectRepo(projectId, {
        repo_id: repo.id,
        repo_full_name: repo.full_name,
        default_branch: repo.default_branch,
      });
      setShowPicker(false);
      onConnected();
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to connect repository");
    } finally {
      setConnecting(false);
    }
  }

  const filtered = repos.filter((r) =>
    r.full_name.toLowerCase().includes(search.toLowerCase()),
  );

  if (!showPicker) {
    return (
      <div className="mt-3 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/50 p-4">
        <p className="text-sm text-zinc-400">
          Connect a GitHub repository to enable automatic builds and deploys.
        </p>
        <button
          onClick={handleOpen}
          className="mt-2 rounded-md bg-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-zinc-300"
        >
          Connect repository
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-100">
          Select a repository
        </h3>
        <button
          onClick={() => setShowPicker(false)}
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          Cancel
        </button>
      </div>

      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

      {loadingRepos ? (
        <p className="text-sm text-zinc-500">Loading repositories...</p>
      ) : (
        <>
          <input
            type="text"
            placeholder="Search repositories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mb-3 block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          />
          <div className="max-h-60 space-y-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="py-4 text-center text-sm text-zinc-500">
                {repos.length === 0
                  ? "No repositories found. Connect your GitHub account in Settings first."
                  : "No matching repositories."}
              </p>
            ) : (
              filtered.map((repo) => (
                <button
                  key={repo.id}
                  onClick={() => handleConnect(repo)}
                  disabled={connecting}
                  className="flex w-full items-center justify-between rounded-md border border-zinc-800 px-3 py-2 text-left hover:bg-zinc-800/50 disabled:opacity-50"
                >
                  <div>
                    <p className="text-sm font-medium text-zinc-100">
                      {repo.full_name}
                    </p>
                    {repo.description && (
                      <p className="text-xs text-zinc-500 truncate max-w-md">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {repo.private && (
                      <span className="rounded bg-amber-950/30 px-1.5 py-0.5 text-xs text-amber-400">
                        private
                      </span>
                    )}
                    <span className="text-xs text-zinc-500">
                      {repo.default_branch}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Deploys tab                                                            */
/* ---------------------------------------------------------------------- */

function DeploysTab({
  deploys,
  environments,
  projectId,
  project,
  onUpdate,
}: {
  deploys: Deploy[];
  environments: Environment[];
  projectId: string;
  project: Project;
  onUpdate: () => void;
}) {
  const [rolling, setRolling] = useState<string | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [destroyTarget, setDestroyTarget] = useState<Deploy | null>(null);
  const [destroying, setDestroying] = useState(false);
  const [actionError, setActionError] = useState("");

  const envMap = Object.fromEntries(environments.map((e) => [e.id, e]));

  async function handleRollback(deployId: string) {
    setRolling(deployId);
    setActionError("");
    try {
      await api.deploys.rollback(deployId, "Rolled back from UI");
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setActionError(err.detail);
    } finally {
      setRolling(null);
    }
  }

  async function handleStop(deployId: string) {
    setStopping(deployId);
    setActionError("");
    try {
      await api.deploys.stop(deployId);
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setActionError(err.detail);
    } finally {
      setStopping(null);
    }
  }

  async function handleStart(deployId: string) {
    setStarting(deployId);
    setActionError("");
    try {
      await api.deploys.start(deployId);
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setActionError(err.detail);
    } finally {
      setStarting(null);
    }
  }

  async function handleDestroy() {
    if (!destroyTarget) return;
    setDestroying(true);
    setActionError("");
    try {
      await api.deploys.destroy(destroyTarget.id);
      setDestroyTarget(null);
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setActionError(err.detail);
    } finally {
      setDestroying(false);
    }
  }

  if (deploys.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No deploys yet. Push to your connected repo to trigger a deploy.
      </p>
    );
  }

  return (
    <div>
      {/* Production URL banner */}
      {project.production_url && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-green-800 bg-green-950/30 px-4 py-3">
          <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Production URL</p>
            <a
              href={project.production_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-zinc-100 hover:text-brand-600 transition-colors truncate block"
            >
              {project.production_url.replace(/^https?:\/\//, "")}
            </a>
          </div>
          <span className="text-xs text-zinc-500">Always points to active deploy</span>
        </div>
      )}

      {actionError && (
        <div className="mb-3 rounded-md border border-red-800 bg-red-950/30 px-3 py-2">
          <p className="text-xs text-red-400">{actionError}</p>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <table className="min-w-full divide-y divide-zinc-800 text-sm">
          <thead className="bg-zinc-900/50">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-zinc-500">
                Status
              </th>
              <th className="px-4 py-2 text-left font-medium text-zinc-500">
                Environment
              </th>
              <th className="px-4 py-2 text-left font-medium text-zinc-500">
                URLs
              </th>
              <th className="px-4 py-2 text-left font-medium text-zinc-500">
                Created
              </th>
              <th className="px-4 py-2 text-right font-medium text-zinc-500">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {deploys.map((d) => {
              const isActive = d.status === "active" || d.status === "healthy";
              const isStopped = d.status === "stopped";
              const isTerminal = d.status === "rolled_back" || d.status === "superseded";
              const canRollback = isActive;
              const canStop = isActive;
              const canStart = isStopped;
              const canDestroy = !isTerminal;

              return (
                <tr key={d.id} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2">
                    <Link href={`/dashboard/${projectId}/deploys/${d.id}`}>
                      <StatusBadge status={d.status} />
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-zinc-300">
                    {envMap[d.env_id]?.name ?? d.env_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-2">
                    {d.url ? (
                      <div className="space-y-0.5">
                        <a
                          href={d.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-600 hover:underline text-xs block"
                          title="Immutable deploy URL"
                        >
                          {d.url.replace(/^https?:\/\//, "")}
                        </a>
                        {isActive && project.production_url && (
                          <a
                            href={project.production_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-green-400 hover:underline text-xs block"
                            title="Production URL (always points to active deploy)"
                          >
                            {project.production_url.replace(/^https?:\/\//, "")}
                          </a>
                        )}
                      </div>
                    ) : (
                      <span className="text-zinc-500">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-zinc-500">
                    {timeAgo(d.created_at)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {/* Start (for stopped deploys) */}
                      {canStart && (
                        <button
                          onClick={() => handleStart(d.id)}
                          disabled={starting === d.id}
                          className="inline-flex items-center gap-1 rounded-md border border-green-800 px-2 py-1 text-xs font-medium text-green-400 hover:bg-green-950/30 disabled:opacity-50 transition-colors"
                          title="Start container"
                        >
                          {starting === d.id ? (
                            "Starting..."
                          ) : (
                            <>
                              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                              </svg>
                              Start
                            </>
                          )}
                        </button>
                      )}
                      {/* Stop (for active deploys) */}
                      {canStop && (
                        <button
                          onClick={() => handleStop(d.id)}
                          disabled={stopping === d.id}
                          className="inline-flex items-center gap-1 rounded-md border border-amber-800 px-2 py-1 text-xs font-medium text-amber-400 hover:bg-amber-950/30 disabled:opacity-50 transition-colors"
                          title="Stop container (preserves data)"
                        >
                          {stopping === d.id ? (
                            "Stopping..."
                          ) : (
                            <>
                              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z" />
                              </svg>
                              Stop
                            </>
                          )}
                        </button>
                      )}
                      {/* Rollback (for active deploys) */}
                      {canRollback && (
                        <button
                          onClick={() => handleRollback(d.id)}
                          disabled={rolling === d.id}
                          className="inline-flex items-center gap-1 rounded-md border border-orange-800 px-2 py-1 text-xs font-medium text-orange-400 hover:bg-orange-950/30 disabled:opacity-50 transition-colors"
                          title="Rollback to previous successful deploy"
                        >
                          {rolling === d.id ? (
                            "Rolling back..."
                          ) : (
                            <>
                              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
                              </svg>
                              Rollback
                            </>
                          )}
                        </button>
                      )}
                      {/* Destroy (for any non-terminal deploy) */}
                      {canDestroy && (
                        <button
                          onClick={() => setDestroyTarget(d)}
                          className="inline-flex items-center gap-1 rounded-md border border-red-800 px-2 py-1 text-xs font-medium text-red-400 hover:bg-red-950/30 transition-colors"
                          title="Destroy deploy and container"
                        >
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                          Destroy
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Destroy confirmation modal */}
      <ConfirmModal
        open={!!destroyTarget}
        onClose={() => setDestroyTarget(null)}
        onConfirm={handleDestroy}
        title="Destroy deployment"
        description={`Permanently destroy this deployment? This will stop and remove the container, Nginx routing, and DNS entry. The deploy will be marked as rolled back.${
          destroyTarget?.status === "active"
            ? " WARNING: This is the active production deploy — the production URL will stop working."
            : ""
        }`}
        confirmLabel="Destroy"
        variant="danger"
        loading={destroying}
      />
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Builds tab                                                             */
/* ---------------------------------------------------------------------- */

function BuildsTab({
  builds,
  project,
  projectId,
  onUpdate,
}: {
  builds: Build[];
  project: Project;
  projectId: string;
  onUpdate: () => void;
}) {
  const [viewingLogs, setViewingLogs] = useState<string | null>(null);
  const [restLogs, setRestLogs] = useState<BuildLogsResponse | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildError, setRebuildError] = useState("");
  const [deployLogs, setDeployLogs] = useState<DeployLogsResponse | null>(null);
  const logsEndRef = useRef<HTMLPreElement>(null);
  const deployLogsEndRef = useRef<HTMLPreElement>(null);

  // --- Determine build state ---
  const hasActiveBuild = builds.some(
    (b) => b.status === "building" || b.status === "queued",
  );

  const viewedBuild = viewingLogs
    ? builds.find((b) => b.id === viewingLogs)
    : null;
  const viewedBuildRunning =
    viewedBuild?.status === "building" || viewedBuild?.status === "queued";

  // --- SSE stream for build logs (replaces 3s polling) ---
  const buildStreamUrl = useMemo(() => {
    if (!viewingLogs || !viewedBuildRunning) return null;
    return api.builds.logsStreamUrl(projectId, viewingLogs);
  }, [viewingLogs, viewedBuildRunning, projectId]);

  const token = typeof window !== "undefined" ? getToken() : null;
  const buildLogStream = useLogStream(buildStreamUrl, token);

  // Merge: use SSE logs while streaming, fallback to REST logs
  const displayBuildLogs = viewedBuildRunning
    ? buildLogStream.logs ?? restLogs?.logs ?? null
    : restLogs?.logs ?? null;

  // --- SSE stream for deploy logs (when build triggers a deploy) ---
  // Look up the most recent deploy associated with the viewed build
  const [linkedDeployId, setLinkedDeployId] = useState<string | null>(null);

  // When viewing a build, check if there's a linked deploy
  useEffect(() => {
    if (!viewingLogs) {
      setLinkedDeployId(null);
      setDeployLogs(null);
      return;
    }
    // Check for deploy triggered by this build via the deploys list
    // The deploy's artifact_id matches the build's artifact
    api.deploys.list(projectId, 0, 50).then((res) => {
      // Find the most recent deploy (deploys are ordered by created_at desc)
      // We can't directly link build->deploy in the current schema, so
      // we show the most recent active/in-progress deploy for context
      const inProgressDeploy = res.items.find(
        (d) => !["active", "stopped", "failed", "rolled_back", "superseded"].includes(d.status),
      );
      if (inProgressDeploy) {
        setLinkedDeployId(inProgressDeploy.id);
      }
    }).catch(() => {
      // ignore
    });
  }, [viewingLogs, projectId]);

  const deployStreamUrl = useMemo(() => {
    if (!linkedDeployId) return null;
    return api.deploys.logsStreamUrl(projectId, linkedDeployId);
  }, [linkedDeployId, projectId]);

  const deployLogStream = useLogStream(deployStreamUrl, token);

  // For terminal deploys, fetch logs once via REST
  useEffect(() => {
    if (!linkedDeployId) return;
    if (deployLogStream.isStreaming) return; // SSE is handling it
    api.deploys.logs(projectId, linkedDeployId).then((res) => {
      setDeployLogs(res);
    }).catch(() => {
      // ignore
    });
  }, [linkedDeployId, projectId, deployLogStream.isStreaming]);

  const displayDeployLogs = deployLogStream.logs ?? deployLogs?.logs ?? null;

  // Poll the builds list every 5s while any build is active
  useEffect(() => {
    if (!hasActiveBuild) return;

    const interval = setInterval(() => {
      onUpdate();
    }, 5000);

    return () => clearInterval(interval);
  }, [hasActiveBuild, onUpdate]);

  // Auto-scroll logs to bottom when they update
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollTop = logsEndRef.current.scrollHeight;
    }
  }, [displayBuildLogs]);

  useEffect(() => {
    if (deployLogsEndRef.current) {
      deployLogsEndRef.current.scrollTop = deployLogsEndRef.current.scrollHeight;
    }
  }, [displayDeployLogs]);

  async function handleViewLogs(buildId: string) {
    if (viewingLogs === buildId) {
      setViewingLogs(null);
      setRestLogs(null);
      setLinkedDeployId(null);
      setDeployLogs(null);
      return;
    }
    setViewingLogs(buildId);
    setLoadingLogs(true);
    try {
      const data = await api.builds.logs(projectId, buildId);
      setRestLogs(data);
    } catch {
      setRestLogs(null);
    } finally {
      setLoadingLogs(false);
    }
  }

  async function handleRebuild() {
    setRebuilding(true);
    setRebuildError("");
    try {
      await api.builds.trigger(projectId);
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setRebuildError(err.detail);
      else setRebuildError("Failed to trigger rebuild");
    } finally {
      setRebuilding(false);
    }
  }

  const hasRepo = !!project.repo;

  return (
    <div>
      {/* Header with rebuild button */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-100">
          {builds.length > 0
            ? `${builds.length} build${builds.length !== 1 ? "s" : ""}`
            : "No builds yet"}
        </h3>
        {hasRepo && (
          <button
            onClick={handleRebuild}
            disabled={rebuilding}
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-zinc-300 disabled:opacity-50"
          >
            {rebuilding ? (
              "Triggering..."
            ) : (
              <>
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182"
                  />
                </svg>
                Rebuild
              </>
            )}
          </button>
        )}
      </div>

      {rebuildError && (
        <p className="mb-3 text-xs text-red-400">{rebuildError}</p>
      )}

      {builds.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          {hasRepo
            ? "No builds yet. Click Rebuild to trigger the first build."
            : "No builds yet. Connect a repository to start building."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="min-w-full divide-y divide-zinc-800 text-sm">
            <thead className="bg-zinc-900/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Status
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Trigger
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Commit
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Branch
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Started
                </th>
                <th className="px-4 py-2 text-left font-medium text-zinc-500">
                  Duration
                </th>
                <th className="px-4 py-2 text-right font-medium text-zinc-500">
                  Logs
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {builds.map((b) => (
                <tr key={b.id} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2">
                    <StatusBadge status={b.status} />
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-500">
                    {b.trigger === "push" ? (
                      <span className="inline-flex items-center rounded bg-blue-950/30 px-1.5 py-0.5 text-blue-400">
                        push
                      </span>
                    ) : b.trigger === "pull_request" ? (
                      <span className="inline-flex items-center rounded bg-purple-950/30 px-1.5 py-0.5 text-purple-400">
                        PR
                      </span>
                    ) : b.trigger === "manual" ? (
                      <span className="inline-flex items-center rounded bg-amber-950/30 px-1.5 py-0.5 text-amber-400">
                        manual
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded bg-zinc-900/50 px-1.5 py-0.5 text-zinc-400">
                        {b.trigger}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-zinc-300">
                    {b.commit_sha.slice(0, 8)}
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-500">
                    {b.branch ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-zinc-500">
                    {b.started_at ? timeAgo(b.started_at) : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-500">
                    {b.started_at && b.finished_at
                      ? formatDuration(b.started_at, b.finished_at)
                      : b.started_at && !b.finished_at
                        ? "running..."
                        : "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleViewLogs(b.id)}
                      className="text-xs text-brand-600 hover:text-brand-800"
                    >
                      {viewingLogs === b.id ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Build Logs viewer */}
      {viewingLogs && (
        <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-zinc-300">Build Logs</h4>
              {(viewedBuildRunning && buildLogStream.isStreaming) && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                  Live
                </span>
              )}
            </div>
            <button
              onClick={() => {
                setViewingLogs(null);
                setRestLogs(null);
                setLinkedDeployId(null);
                setDeployLogs(null);
              }}
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              Close
            </button>
          </div>
          {loadingLogs ? (
            <p className="text-sm text-zinc-500">Loading logs...</p>
          ) : displayBuildLogs ? (
            <pre
              ref={logsEndRef}
              className="max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-green-400"
            >
              {displayBuildLogs}
            </pre>
          ) : (
            <p className="text-sm text-zinc-500">
              {viewedBuildRunning
                ? "Waiting for build output..."
                : "No logs available for this build."}
            </p>
          )}
        </div>
      )}

      {/* Deploy Logs viewer (shown when a build triggers a deploy) */}
      {viewingLogs && linkedDeployId && (displayDeployLogs || deployLogStream.isStreaming) && (
        <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-2 flex items-center gap-2">
            <h4 className="text-sm font-medium text-zinc-300">Deploy Logs</h4>
            {deployLogStream.isStreaming && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                Live
              </span>
            )}
            <Link
              href={`/dashboard/${projectId}/deploys/${linkedDeployId}`}
              className="ml-auto text-xs text-brand-600 hover:text-brand-800"
            >
              View deploy details
            </Link>
          </div>
          {displayDeployLogs ? (
            <pre
              ref={deployLogsEndRef}
              className="max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-cyan-400"
            >
              {displayDeployLogs}
            </pre>
          ) : (
            <p className="text-sm text-zinc-500">
              Waiting for deploy output...
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Format duration between two ISO timestamps */
function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return "—";
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  return `${mins}m ${remSecs}s`;
}

/* ---------------------------------------------------------------------- */
/*  Environments tab                                                       */
/* ---------------------------------------------------------------------- */

function EnvironmentsTab({
  environments,
  projectId,
  onUpdate,
}: {
  environments: Environment[];
  projectId: string;
  onUpdate: () => void;
}) {
  const { user } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [envType, setEnvType] = useState<"production" | "staging" | "preview">(
    "staging",
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      await api.environments.create(projectId, { name, type: envType });
      setShowCreate(false);
      setName("");
      onUpdate();
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to create environment");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-100">Environments</h3>
        <button
          onClick={() => setShowCreate(true)}
          className="text-xs font-medium text-brand-600 hover:text-brand-700"
        >
          Add environment
        </button>
      </div>

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-4 flex items-end gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Name
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600"
              placeholder="staging"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Type
            </label>
            <select
              value={envType}
              onChange={(e) => setEnvType(e.target.value as typeof envType)}
              className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200"
            >
              <option value="production">Production</option>
              <option value="staging">Staging</option>
              <option value="preview">Preview</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50"
          >
            Create
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(false)}
            className="text-xs text-zinc-500 hover:text-zinc-300"
          >
            Cancel
          </button>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </form>
      )}

      {environments.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No environments configured.
        </p>
      ) : (
        <div className="space-y-2">
          {environments.map((env) => (
            <div
              key={env.id}
              className="flex items-center justify-between rounded-lg border border-zinc-800 px-4 py-3"
            >
              <div>
                <p className="text-sm font-medium text-zinc-100">{env.name}</p>
                <p className="text-xs text-zinc-500">
                  Type: {env.type}
                  {env.vlan_id && ` | VLAN assigned`}
                </p>
              </div>
              <p className="text-xs text-zinc-500">
                {timeAgo(env.created_at)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Settings tab                                                           */
/* ---------------------------------------------------------------------- */

function SettingsTab({
  project,
  projectId,
  onUpdate,
}: {
  project: Project;
  projectId: string;
  onUpdate: () => void;
}) {
  const router = useRouter();
  const [autoDeploy, setAutoDeploy] = useState(project.auto_deploy);
  const [saving, setSaving] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");

  // Build settings state
  const [rootDirectory, setRootDirectory] = useState(project.root_directory ?? "");
  const [buildCommand, setBuildCommand] = useState(project.build_command ?? "");
  const [installCommand, setInstallCommand] = useState(project.install_command ?? "");
  const [outputDirectory, setOutputDirectory] = useState(project.output_directory ?? "");
  const [savingBuild, setSavingBuild] = useState(false);

  // Deploy controls state
  const [deployLocked, setDeployLocked] = useState(project.deploy_locked ?? false);
  const [healthCheckPath, setHealthCheckPath] = useState(project.health_check_path ?? "");
  const [healthCheckTimeout, setHealthCheckTimeout] = useState(
    project.health_check_timeout?.toString() ?? "",
  );
  const [webhookUrl, setWebhookUrl] = useState(project.webhook_url ?? "");
  const [expiresAt, setExpiresAt] = useState(
    project.expires_at ? project.expires_at.slice(0, 16) : "",
  );
  const [savingDeploy, setSavingDeploy] = useState(false);

  // Modal state
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Track whether build settings have changed
  const buildSettingsChanged =
    (rootDirectory || null) !== (project.root_directory ?? null) ||
    (buildCommand || null) !== (project.build_command ?? null) ||
    (installCommand || null) !== (project.install_command ?? null) ||
    (outputDirectory || null) !== (project.output_directory ?? null);

  // Track whether deploy control settings have changed
  const deployControlsChanged =
    deployLocked !== (project.deploy_locked ?? false) ||
    (healthCheckPath || null) !== (project.health_check_path ?? null) ||
    (healthCheckTimeout || null) !== (project.health_check_timeout?.toString() ?? null) ||
    (webhookUrl || null) !== (project.webhook_url ?? null) ||
    (expiresAt || null) !== (project.expires_at ? project.expires_at.slice(0, 16) : null);

  async function handleToggleAutoDeploy() {
    const newValue = !autoDeploy;
    setAutoDeploy(newValue);
    setSaving(true);
    setMessage("");
    try {
      await api.projects.update(projectId, { auto_deploy: newValue });
      setMessage(
        newValue
          ? "Auto-deploy enabled. Pushes will trigger builds automatically."
          : "Auto-deploy disabled.",
      );
      onUpdate();
    } catch {
      setAutoDeploy(!newValue); // revert
      setMessage("Failed to update setting.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveBuildSettings() {
    setSavingBuild(true);
    setMessage("");
    try {
      await api.projects.update(projectId, {
        root_directory: rootDirectory || null,
        build_command: buildCommand || null,
        install_command: installCommand || null,
        output_directory: outputDirectory || null,
      });
      setMessage("Build settings saved. Changes will apply to the next build.");
      onUpdate();
    } catch {
      setMessage("Failed to save build settings.");
    } finally {
      setSavingBuild(false);
    }
  }

  async function handleToggleDeployLock() {
    const newValue = !deployLocked;
    setDeployLocked(newValue);
    setSaving(true);
    setMessage("");
    try {
      await api.projects.update(projectId, { deploy_locked: newValue });
      setMessage(
        newValue
          ? "Deploys are now locked. No new deploys will be triggered."
          : "Deploys are now unlocked.",
      );
      onUpdate();
    } catch {
      setDeployLocked(!newValue);
      setMessage("Failed to update deploy lock.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveDeployControls() {
    setSavingDeploy(true);
    setMessage("");
    try {
      await api.projects.update(projectId, {
        health_check_path: healthCheckPath || null,
        health_check_timeout: healthCheckTimeout ? parseInt(healthCheckTimeout, 10) : null,
        webhook_url: webhookUrl || null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
      setMessage("Deploy controls saved.");
      onUpdate();
    } catch {
      setMessage("Failed to save deploy controls.");
    } finally {
      setSavingDeploy(false);
    }
  }

  async function handleDisconnectRepo() {
    setDisconnecting(true);
    try {
      await api.projects.disconnectRepo(projectId);
      setShowDisconnectModal(false);
      onUpdate();
    } catch {
      setMessage("Failed to disconnect repository.");
    } finally {
      setDisconnecting(false);
    }
  }

  async function handleDeleteProject() {
    setDeleting(true);
    try {
      await api.projects.delete(projectId);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) setMessage(err.detail);
      else setMessage("Failed to delete project.");
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Connected repository */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-100">
          Connected Repository
        </h3>
        {project.repo ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-100">
                {project.repo.repo_full_name}
              </p>
              <p className="text-xs text-zinc-500">
                Branch: {project.repo.default_branch} | Provider:{" "}
                {project.repo.provider}
              </p>
            </div>
            <button
              onClick={() => setShowDisconnectModal(true)}
              disabled={disconnecting}
              className="rounded-md border border-red-800 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-950/30 disabled:opacity-50"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            No repository connected. Use the banner above to connect one.
          </p>
        )}
      </div>

      {/* Auto-deploy toggle */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-100">
          Auto Deploy
        </h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-zinc-300">
              Automatically build and deploy when code is pushed to the default
              branch.
            </p>
          </div>
          <button
            onClick={handleToggleAutoDeploy}
            disabled={saving}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 disabled:opacity-50 ${
              autoDeploy ? "bg-brand-600" : "bg-zinc-700"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                autoDeploy ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>

      {/* Build & Development Settings */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h3 className="mb-1 text-sm font-semibold text-zinc-100">
          Build &amp; Development Settings
        </h3>
        <p className="mb-4 text-xs text-zinc-500">
          Override the default build behavior. Leave blank to use auto-detected
          defaults.
        </p>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Root Directory
            </label>
            <input
              type="text"
              value={rootDirectory}
              onChange={(e) => setRootDirectory(e.target.value)}
              placeholder="./"
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              The directory where your source code is located, relative to the
              repo root. Used as the build context.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Install Command
            </label>
            <input
              type="text"
              value={installCommand}
              onChange={(e) => setInstallCommand(e.target.value)}
              placeholder={project.framework === "python" ? "pip install -r requirements.txt" : "npm ci"}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              The command used to install dependencies.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Build Command
            </label>
            <input
              type="text"
              value={buildCommand}
              onChange={(e) => setBuildCommand(e.target.value)}
              placeholder="npm run build"
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              The command used to build your project.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Output Directory
            </label>
            <input
              type="text"
              value={outputDirectory}
              onChange={(e) => setOutputDirectory(e.target.value)}
              placeholder={project.framework === "react" ? "dist" : ""}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              The directory where the build output is located. Used for static
              and React builds.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveBuildSettings}
              disabled={savingBuild || !buildSettingsChanged}
              className="rounded-md bg-brand-500 px-4 py-1.5 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50"
            >
              {savingBuild ? "Saving..." : "Save"}
            </button>
            {buildSettingsChanged && (
              <span className="text-xs text-amber-600">Unsaved changes</span>
            )}
          </div>
        </div>
      </div>

      {/* Framework info */}
      {project.framework && (
        <div className="rounded-lg border border-zinc-800 p-4">
          <h3 className="mb-3 text-sm font-semibold text-zinc-100">
            Detected Framework
          </h3>
          <p className="text-sm text-zinc-300">
            <span className="inline-flex items-center rounded bg-zinc-800 px-2 py-0.5 text-sm font-medium text-zinc-200">
              {project.framework}
            </span>
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            Detected automatically during the first build. Used to generate a
            Dockerfile if one is not present in the repository.
          </p>
        </div>
      )}

      {/* Deploy Controls */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h3 className="mb-1 text-sm font-semibold text-zinc-100">
          Deploy Controls
        </h3>
        <p className="mb-4 text-xs text-zinc-500">
          Manage deploy locks, health checks, notifications, and project
          lifecycle.
        </p>

        {/* Deploy lock toggle */}
        <div className="mb-5 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-100">Deploy Lock</p>
            <p className="text-xs text-zinc-500">
              When locked, no new deploys can be triggered for this project.
            </p>
          </div>
          <button
            onClick={handleToggleDeployLock}
            disabled={saving}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 disabled:opacity-50 ${
              deployLocked ? "bg-red-500" : "bg-zinc-700"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                deployLocked ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Health Check Path
            </label>
            <input
              type="text"
              value={healthCheckPath}
              onChange={(e) => setHealthCheckPath(e.target.value)}
              placeholder="/healthz"
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              Custom HTTP path to check after deploy. Defaults to / if not set.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Health Check Timeout (seconds)
            </label>
            <input
              type="number"
              value={healthCheckTimeout}
              onChange={(e) => setHealthCheckTimeout(e.target.value)}
              placeholder="30"
              min={5}
              max={600}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              Max seconds to wait for the health check to pass (5-600).
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Webhook URL
            </label>
            <input
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              Receive deploy success/failure notifications via webhook (Slack,
              Discord, etc.).
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Project Expiry Date
            </label>
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-xs text-zinc-500">
              Automatically lock deploys after this date. Leave blank for no
              expiry.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveDeployControls}
              disabled={savingDeploy || !deployControlsChanged}
              className="rounded-md bg-brand-500 px-4 py-1.5 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50"
            >
              {savingDeploy ? "Saving..." : "Save"}
            </button>
            {deployControlsChanged && (
              <span className="text-xs text-amber-600">Unsaved changes</span>
            )}
          </div>
        </div>
      </div>

      {/* Danger zone */}
      <div className="rounded-lg border border-red-800 p-4">
        <h3 className="mb-3 text-sm font-semibold text-red-400">
          Danger Zone
        </h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-100">
              Delete this project
            </p>
            <p className="text-xs text-zinc-500">
              Permanently remove this project, its environments, builds, and
              deploys. This action cannot be undone.
            </p>
          </div>
          <button
            onClick={() => setShowDeleteModal(true)}
            disabled={deleting}
            className="rounded-md border border-red-800 bg-zinc-900/50 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-950/30 disabled:opacity-50"
          >
            Delete Project
          </button>
        </div>
      </div>

      {message && (
        <p className="text-xs text-zinc-400">{message}</p>
      )}

      {/* Disconnect repo modal */}
      <ConfirmModal
        open={showDisconnectModal}
        onClose={() => setShowDisconnectModal(false)}
        onConfirm={handleDisconnectRepo}
        title="Disconnect repository"
        description="Disconnect this repository? Existing builds and deploys will not be affected."
        confirmLabel="Disconnect"
        variant="danger"
        loading={disconnecting}
      />

      {/* Delete project modal */}
      <ConfirmModal
        open={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleDeleteProject}
        title="Delete project"
        description={`Permanently delete "${project.name}"? This will remove all environments, builds, and deploys. This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleting}
      />
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Members tab                                                            */
/* ---------------------------------------------------------------------- */

function MembersTab({
  project,
  projectId,
}: {
  project: Project;
  projectId: string;
}) {
  const { user } = useAuth();
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Add member state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");

  // Remove member state
  const [removeTarget, setRemoveTarget] = useState<ProjectMember | null>(null);
  const [removing, setRemoving] = useState(false);

  const searchRef = useRef<HTMLDivElement>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isOwner = user?.id === project.owner_id;
  const isStaffOrFaculty =
    user?.role === "JAS-Staff" || user?.role === "JAS-Faculty";
  const canManageMembers = isOwner || isStaffOrFaculty;

  const fetchMembers = useCallback(async () => {
    try {
      const res = await api.projects.members.list(projectId);
      setMembers(res.items);
    } catch {
      setError("Failed to load members");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  // Close search results when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Debounced user search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);

    if (searchQuery.trim().length === 0) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }

    searchTimerRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.users.search(searchQuery.trim());
        // Filter out the owner and existing members
        const memberIds = new Set(members.map((m) => m.user_id));
        memberIds.add(project.owner_id);
        setSearchResults(res.items.filter((u) => !memberIds.has(u.id)));
        setShowResults(true);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [searchQuery, members, project.owner_id]);

  async function handleAddMember(userId: string) {
    setAdding(true);
    setAddError("");
    try {
      await api.projects.members.add(projectId, { user_id: userId });
      setSearchQuery("");
      setSearchResults([]);
      setShowResults(false);
      await fetchMembers();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setAddError("User is already a member of this project");
      } else {
        setAddError("Failed to add member");
      }
    } finally {
      setAdding(false);
    }
  }

  async function handleRemoveMember() {
    if (!removeTarget) return;
    setRemoving(true);
    try {
      await api.projects.members.remove(projectId, removeTarget.user_id);
      setRemoveTarget(null);
      await fetchMembers();
    } catch {
      setError("Failed to remove member");
    } finally {
      setRemoving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading members...</p>;
  }

  if (error && members.length === 0) {
    return <p className="text-sm text-red-400">{error}</p>;
  }

  return (
    <div className="space-y-6">
      {/* Owner display */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-100">Owner</h3>
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-950 text-sm font-semibold text-brand-400">
            {(user?.id === project.owner_id ? user?.display_name : "O")
              ?.charAt(0)
              .toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-100">
              {user?.id === project.owner_id
                ? user?.display_name
                : "Project Owner"}
            </p>
            <p className="text-xs text-zinc-500">
              {user?.id === project.owner_id ? user?.username : ""}
            </p>
          </div>
          <span className="ml-auto inline-flex items-center rounded-md bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-400">
            Owner
          </span>
        </div>
      </div>

      {/* Contributors list */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-100">
            Contributors
            {members.length > 0 && (
              <span className="ml-1.5 rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-normal text-zinc-500">
                {members.length}
              </span>
            )}
          </h3>
        </div>

        {/* Add member search (owner / staff / faculty only) */}
        {canManageMembers && (
          <div ref={searchRef} className="relative mb-4">
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => {
                  if (searchResults.length > 0) setShowResults(true);
                }}
                placeholder="Search users to add..."
                className="block w-full rounded-md border border-zinc-800 bg-zinc-950 py-1.5 pl-9 pr-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
                disabled={adding}
              />
              {searching && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-brand-600" />
                </div>
              )}
            </div>

            {/* Search results dropdown */}
            {showResults && (
              <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-zinc-800 bg-zinc-900 shadow-lg">
                {searchResults.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-zinc-500">
                    {searchQuery.trim()
                      ? "No users found"
                      : "Type to search..."}
                  </p>
                ) : (
                  searchResults.map((u) => (
                    <button
                      key={u.id}
                      onClick={() => handleAddMember(u.id)}
                      disabled={adding}
                      className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-zinc-800/50 disabled:opacity-50"
                    >
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-800 text-xs font-semibold text-zinc-400">
                        {u.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-zinc-100">
                          {u.display_name}
                        </p>
                        <p className="truncate text-xs text-zinc-500">
                          {u.username}
                        </p>
                      </div>
                      <span className="flex-shrink-0 text-xs text-brand-600">
                        Add
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}

            {addError && (
              <p className="mt-1 text-xs text-red-400">{addError}</p>
            )}
          </div>
        )}

        {/* Member list */}
        {members.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No contributors yet.
            {canManageMembers && " Search for users above to add them."}
          </p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {members.map((member) => {
              const isSelf = member.user_id === user?.id;
              const canRemove = canManageMembers || isSelf;
              return (
                <div
                  key={member.id}
                  className="flex items-center gap-3 py-2.5"
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-sm font-semibold text-zinc-400">
                    {member.display_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-zinc-100">
                      {member.display_name}
                      {isSelf && (
                        <span className="ml-1 text-xs font-normal text-zinc-500">
                          (you)
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-zinc-500">{member.username}</p>
                  </div>
                  <span className="inline-flex items-center rounded-md bg-brand-950/50 px-2 py-0.5 text-xs font-medium text-brand-400 ring-1 ring-inset ring-brand-800">
                    {member.role}
                  </span>
                  {canRemove && (
                    <button
                      onClick={() => setRemoveTarget(member)}
                      className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-red-400 transition-colors"
                      title={isSelf ? "Leave project" : "Remove member"}
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={2}
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Remove / Leave confirmation modal */}
      <ConfirmModal
        open={!!removeTarget}
        onClose={() => setRemoveTarget(null)}
        onConfirm={handleRemoveMember}
        title={
          removeTarget?.user_id === user?.id
            ? "Leave project"
            : "Remove member"
        }
        description={
          removeTarget?.user_id === user?.id
            ? "You will no longer have access to this project. You can be re-added by the owner."
            : `Remove ${removeTarget?.display_name} from this project? They will lose access immediately.`
        }
        confirmLabel={
          removeTarget?.user_id === user?.id ? "Leave" : "Remove"
        }
        variant="danger"
        loading={removing}
      />
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Secrets tab link                                                       */
/* ---------------------------------------------------------------------- */

function SecretsTabLink({ projectId }: { projectId: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-zinc-500">
        Manage secrets for this project.
      </p>
      <Link
        href={`/dashboard/${projectId}/secrets`}
        className="mt-2 inline-block text-sm font-medium text-brand-600 hover:text-brand-700"
      >
        Go to secrets management
      </Link>
    </div>
  );
}
