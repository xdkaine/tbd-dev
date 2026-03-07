/* ------------------------------------------------------------------ */
/*  API client — fetch wrapper with JWT auth                          */
/* ------------------------------------------------------------------ */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

/** Error thrown by API calls. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/** Read the stored JWT from localStorage. */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("tbd_token");
}

/** Store a JWT in localStorage. */
export function setToken(token: string): void {
  localStorage.setItem("tbd_token", token);
}

/** Remove the stored JWT. */
export function clearToken(): void {
  localStorage.removeItem("tbd_token");
}

/** Core fetch wrapper. Attaches Authorization header when a token exists. */
async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* no json body */
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json();
}

/* ------------------------------------------------------------------ */
/*  Typed API methods                                                  */
/* ------------------------------------------------------------------ */

import type {
  ActivityResponse,
  AdminProjectListResponse,
  AdminStats,
  AdminUser,
  AdminUserListResponse,
  AuditLogListResponse,
  Build,
  BuildListResponse,
  BuildLogsResponse,
  ConnectRepoRequest,
  Deploy,
  DeployListResponse,
  DeployLogsResponse,
  DeployTriggerResponse,
  Environment,
  EnvironmentCreate,
  EnvironmentListResponse,
  GitHubRepo,
  LoginRequest,
  NetworkPolicy,
  NetworkPolicyCreate,
  NetworkPolicyListResponse,
  NetworkPolicyUpdate,
  Project,
  ProjectCreate,
  ProjectListResponse,
  ProjectMember,
  ProjectMemberAdd,
  ProjectMemberListResponse,
  ProjectUpdate,
  Quota,
  QuotaListResponse,
  QuotaUpdate,
  QueueStatus,
  Repo,
  Secret,
  SecretCreate,
  SecretListResponse,
  StudentDetail,
  StudentListResponse,
  Template,
  TemplateDeployRequest,
  TemplateDeployResponse,
  TemplateListResponse,
  TokenResponse,
  TrendResponse,
  UserInfo,
  UserSearchResponse,
  Vlan,
  VlanListResponse,
} from "./types";

/* Auth */
export const api = {
  auth: {
    login: (body: LoginRequest) =>
      request<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    me: () => request<UserInfo>("/auth/me"),
    githubAuthorizeUrl: () =>
      request<{ authorize_url: string }>("/auth/github"),
    githubUnlink: () =>
      request<void>("/auth/github/link", { method: "DELETE" }),
  },

  /* Projects */
  projects: {
    list: (skip = 0, limit = 50) =>
      request<ProjectListResponse>(`/projects?skip=${skip}&limit=${limit}`),
    get: (id: string) => request<Project>(`/projects/${id}`),
    create: (body: ProjectCreate) =>
      request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    update: (id: string, body: ProjectUpdate) =>
      request<Project>(`/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    connectRepo: (projectId: string, body: ConnectRepoRequest) =>
      request<Repo>(`/projects/${projectId}/repo`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    disconnectRepo: (projectId: string) =>
      request<void>(`/projects/${projectId}/repo`, {
        method: "DELETE",
      }),
    delete: (id: string) =>
      request<void>(`/projects/${id}`, {
        method: "DELETE",
      }),

    /* Members */
    members: {
      list: (projectId: string) =>
        request<ProjectMemberListResponse>(
          `/projects/${projectId}/members`,
        ),
      add: (projectId: string, body: ProjectMemberAdd) =>
        request<ProjectMember>(`/projects/${projectId}/members`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      remove: (projectId: string, userId: string) =>
        request<void>(`/projects/${projectId}/members/${userId}`, {
          method: "DELETE",
        }),
    },
  },

  /* Users */
  users: {
    search: (q: string, limit = 20) =>
      request<UserSearchResponse>(
        `/users/search?q=${encodeURIComponent(q)}&limit=${limit}`,
      ),
  },

  /* Environments */
  environments: {
    list: (projectId: string) =>
      request<EnvironmentListResponse>(
        `/projects/${projectId}/environments`,
      ),
    create: (projectId: string, body: EnvironmentCreate) =>
      request<Environment>(`/projects/${projectId}/environments`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    delete: (projectId: string, envId: string) =>
      request<void>(`/projects/${projectId}/environments/${envId}`, {
        method: "DELETE",
      }),
  },

  /* Builds */
  builds: {
    list: (projectId: string, skip = 0, limit = 50) =>
      request<BuildListResponse>(
        `/projects/${projectId}/builds?skip=${skip}&limit=${limit}`,
      ),
    get: (projectId: string, buildId: string) =>
      request<Build>(`/projects/${projectId}/builds/${buildId}`),
    logs: (projectId: string, buildId: string) =>
      request<BuildLogsResponse>(
        `/projects/${projectId}/builds/${buildId}/logs`,
      ),
    logsStreamUrl: (projectId: string, buildId: string) =>
      `${API_BASE}/projects/${projectId}/builds/${buildId}/logs/stream`,
    trigger: (projectId: string) =>
      request<Build>(`/projects/${projectId}/builds/trigger`, {
        method: "POST",
      }),
    deploy: (projectId: string, buildId: string, env: string) =>
      request<DeployTriggerResponse>(
        `/projects/${projectId}/builds/${buildId}/deploy`,
        {
          method: "POST",
          body: JSON.stringify({ env }),
        },
      ),
  },

  /* Deploys */
  deploys: {
    list: (projectId: string, skip = 0, limit = 50) =>
      request<DeployListResponse>(
        `/projects/${projectId}/deploys?skip=${skip}&limit=${limit}`,
      ),
    logs: (projectId: string, deployId: string) =>
      request<DeployLogsResponse>(
        `/projects/${projectId}/deploys/${deployId}/logs`,
      ),
    logsStreamUrl: (projectId: string, deployId: string) =>
      `${API_BASE}/projects/${projectId}/deploys/${deployId}/logs/stream`,
    rollback: (deployId: string, reason?: string) =>
      request<Deploy>(`/deploys/${deployId}/rollback`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
    promote: (deployId: string) =>
      request<Deploy>(`/deploys/${deployId}/promote`, {
        method: "POST",
      }),
    destroy: (deployId: string) =>
      request<Deploy>(`/deploys/${deployId}`, {
        method: "DELETE",
      }),
    stop: (deployId: string) =>
      request<Deploy>(`/deploys/${deployId}/stop`, {
        method: "POST",
      }),
    start: (deployId: string) =>
      request<Deploy>(`/deploys/${deployId}/start`, {
        method: "POST",
      }),
    queueStatus: (projectId: string, envId: string) =>
      request<QueueStatus>(
        `/projects/${projectId}/environments/${envId}/queue`,
      ),
  },

  /* Secrets */
  secrets: {
    list: (projectId: string) =>
      request<SecretListResponse>(`/projects/${projectId}/secrets`),
    create: (projectId: string, body: SecretCreate) =>
      request<Secret>(`/projects/${projectId}/secrets`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    delete: (projectId: string, key: string) =>
      request<void>(`/projects/${projectId}/secrets/${key}`, {
        method: "DELETE",
      }),
  },

  /* Networks */
  networks: {
    listVlans: () => request<VlanListResponse>("/networks/vlans"),
    getProjectVlan: (projectId: string) =>
      request<Vlan>(`/networks/vlans/${projectId}`),
    reserveVlan: (projectId: string) =>
      request<Vlan>("/networks/vlans/reserve", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      }),
    releaseVlan: (projectId: string) =>
      request<void>(`/networks/vlans/${projectId}`, { method: "DELETE" }),
  },

  /* Audit */
  audit: {
    list: (params?: {
      skip?: number;
      limit?: number;
      action?: string;
      target_type?: string;
      actor_user_id?: string;
      since?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.skip !== undefined) qs.set("skip", String(params.skip));
      if (params?.limit !== undefined) qs.set("limit", String(params.limit));
      if (params?.action) qs.set("action", params.action);
      if (params?.target_type) qs.set("target_type", params.target_type);
      if (params?.actor_user_id) qs.set("actor_user_id", params.actor_user_id);
      if (params?.since) qs.set("since", params.since);
      return request<AuditLogListResponse>(`/audits?${qs.toString()}`);
    },
  },

  /* GitHub integration */
  github: {
    listRepos: () => request<GitHubRepo[]>("/auth/github/repos"),
  },

  /* Templates */
  templates: {
    list: () => request<TemplateListResponse>("/templates"),
    get: (slug: string) => request<Template>(`/templates/${slug}`),
    deploy: (slug: string, body: TemplateDeployRequest) =>
      request<TemplateDeployResponse>(`/templates/${slug}/deploy`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  /* Admin */
  admin: {
    stats: () => request<AdminStats>("/admin/stats"),

    trends: (days = 30) =>
      request<TrendResponse>(`/admin/stats/trends?days=${days}`),

    activity: (limit = 30) =>
      request<ActivityResponse>(`/admin/activity?limit=${limit}`),

    projects: (params?: {
      skip?: number;
      limit?: number;
      search?: string;
      status?: string;
      tag?: string;
      sort?: string;
      order?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.skip !== undefined) qs.set("skip", String(params.skip));
      if (params?.limit !== undefined) qs.set("limit", String(params.limit));
      if (params?.search) qs.set("search", params.search);
      if (params?.status) qs.set("status", params.status);
      if (params?.tag) qs.set("tag", params.tag);
      if (params?.sort) qs.set("sort", params.sort);
      if (params?.order) qs.set("order", params.order);
      return request<AdminProjectListResponse>(`/admin/projects?${qs.toString()}`);
    },

    students: {
      list: (params?: {
        skip?: number;
        limit?: number;
        search?: string;
        sort?: string;
        order?: string;
      }) => {
        const qs = new URLSearchParams();
        if (params?.skip !== undefined) qs.set("skip", String(params.skip));
        if (params?.limit !== undefined) qs.set("limit", String(params.limit));
        if (params?.search) qs.set("search", params.search);
        if (params?.sort) qs.set("sort", params.sort);
        if (params?.order) qs.set("order", params.order);
        return request<StudentListResponse>(`/admin/students?${qs.toString()}`);
      },
      get: (userId: string) => request<StudentDetail>(`/admin/students/${userId}`),
    },

    /* Quotas */
    quotas: {
      list: (params?: { skip?: number; limit?: number; search?: string }) => {
        const qs = new URLSearchParams();
        if (params?.skip !== undefined) qs.set("skip", String(params.skip));
        if (params?.limit !== undefined) qs.set("limit", String(params.limit));
        if (params?.search) qs.set("search", params.search);
        return request<QuotaListResponse>(`/admin/quotas?${qs.toString()}`);
      },
      get: (projectId: string) =>
        request<Quota>(`/admin/quotas/${projectId}`),
      update: (projectId: string, body: QuotaUpdate) =>
        request<Quota>(`/admin/quotas/${projectId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        }),
    },

    /* Users */
    users: {
      list: (params?: { skip?: number; limit?: number; search?: string; role?: string }) => {
        const qs = new URLSearchParams();
        if (params?.skip !== undefined) qs.set("skip", String(params.skip));
        if (params?.limit !== undefined) qs.set("limit", String(params.limit));
        if (params?.search) qs.set("search", params.search);
        if (params?.role) qs.set("role", params.role);
        return request<AdminUserListResponse>(`/admin/users?${qs.toString()}`);
      },
      get: (userId: string) => request<AdminUser>(`/admin/users/${userId}`),
      updateRole: (userId: string, role: string) =>
        request<AdminUser>(`/admin/users/${userId}/role`, {
          method: "PATCH",
          body: JSON.stringify({ role }),
        }),
    },

    /* Network Policies */
    networkPolicies: {
      list: (params?: { skip?: number; limit?: number; project_id?: string; direction?: string }) => {
        const qs = new URLSearchParams();
        if (params?.skip !== undefined) qs.set("skip", String(params.skip));
        if (params?.limit !== undefined) qs.set("limit", String(params.limit));
        if (params?.project_id) qs.set("project_id", params.project_id);
        if (params?.direction) qs.set("direction", params.direction);
        return request<NetworkPolicyListResponse>(`/admin/network-policies?${qs.toString()}`);
      },
      create: (body: NetworkPolicyCreate) =>
        request<NetworkPolicy>("/admin/network-policies", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      update: (policyId: string, body: NetworkPolicyUpdate) =>
        request<NetworkPolicy>(`/admin/network-policies/${policyId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        }),
      delete: (policyId: string) =>
        request<void>(`/admin/network-policies/${policyId}`, {
          method: "DELETE",
        }),
    },
  },
};
