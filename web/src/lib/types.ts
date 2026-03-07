/* ------------------------------------------------------------------ */
/*  TypeScript types mirroring the API Pydantic schemas               */
/* ------------------------------------------------------------------ */

/* Auth */
export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserInfo {
  id: string;
  username: string;
  display_name: string;
  email: string;
  role: "JAS_Developer" | "JAS-Staff" | "JAS-Faculty";
  github_username: string | null;
  created_at: string;
}

/* Projects */
export interface Repo {
  id: string;
  provider: string;
  repo_id: string;
  repo_full_name: string | null;
  default_branch: string;
  install_id: string | null;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  repo_url: string | null;
  owner_id: string;
  default_env: string;
  auto_deploy: boolean;
  framework: string | null;
  root_directory: string | null;
  build_command: string | null;
  install_command: string | null;
  output_directory: string | null;
  health_check_path: string | null;
  health_check_timeout: number | null;
  webhook_url: string | null;
  deploy_locked: boolean;
  expires_at: string | null;
  production_url: string | null;
  repo: Repo | null;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
  slug: string;
  repo_url?: string | null;
  default_env?: string;
}

export interface ProjectUpdate {
  name?: string | null;
  repo_url?: string | null;
  default_env?: string | null;
  auto_deploy?: boolean | null;
  framework?: string | null;
  root_directory?: string | null;
  build_command?: string | null;
  install_command?: string | null;
  output_directory?: string | null;
  health_check_path?: string | null;
  health_check_timeout?: number | null;
  webhook_url?: string | null;
  deploy_locked?: boolean | null;
  expires_at?: string | null;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
}

/* Project Members */
export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: string;
  username: string;
  display_name: string;
  email: string;
  created_at: string;
}

export interface ProjectMemberAdd {
  user_id: string;
  role?: string;
}

export interface ProjectMemberListResponse {
  items: ProjectMember[];
  total: number;
}

/* User Search */
export interface UserSearchResult {
  id: string;
  username: string;
  display_name: string;
  email: string;
}

export interface UserSearchResponse {
  items: UserSearchResult[];
  total: number;
}

/* Environments */
export interface Environment {
  id: string;
  project_id: string;
  name: string;
  type: "production" | "staging" | "preview";
  vlan_id: string | null;
  created_at: string;
}

export interface EnvironmentCreate {
  name: string;
  type: "production" | "staging" | "preview";
}

export interface EnvironmentListResponse {
  items: Environment[];
  total: number;
}

/* Builds */
export interface Build {
  id: string;
  project_id: string;
  commit_sha: string;
  image_ref: string | null;
  status: string;
  trigger: string;
  branch: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface BuildLogsResponse {
  build_id: string;
  status: string;
  logs: string | null;
}

export interface BuildListResponse {
  items: Build[];
  total: number;
}

/* Deploys */
export type DeployStatus =
  | "queued"
  | "building"
  | "artifact_ready"
  | "provisioning"
  | "healthy"
  | "active"
  | "stopped"
  | "failed"
  | "rolled_back"
  | "superseded";

export interface Deploy {
  id: string;
  env_id: string;
  artifact_id: string | null;
  status: DeployStatus;
  url: string | null;
  created_at: string;
  promoted_at: string | null;
  is_production: boolean;
  container_ip: string | null;
  container_vmid: number | null;
}

export interface DeployListResponse {
  items: Deploy[];
  total: number;
}

export interface DeployLogsResponse {
  deploy_id: string;
  status: string;
  logs: string | null;
}

export interface DeployTriggerResponse {
  deploy_id: string;
  build_id: string;
  artifact_id: string;
  env: string;
  status: string;
  url: string | null;
}

/* Secrets */
export interface Secret {
  id: string;
  project_id: string;
  scope: "project" | "production" | "staging" | "preview";
  key: string;
  created_at: string;
}

export interface SecretCreate {
  key: string;
  value: string;
  scope?: "project" | "production" | "staging" | "preview";
}

export interface SecretListResponse {
  items: Secret[];
  total: number;
}

/* Networks / VLANs */
export interface Vlan {
  id: string;
  vlan_tag: number;
  subnet_cidr: string;
  reserved_by_project_id: string | null;
}

export interface VlanListResponse {
  items: Vlan[];
  total: number;
}

/* Audit */
export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  payload: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
}

/* Queue status */
export interface QueueStatus {
  env_id: string;
  queued: number;
  in_progress: number;
  active: number;
  max_concurrent: number;
  max_queue_size: number;
}

/* GitHub integration */
export interface GitHubRepo {
  id: number;
  full_name: string;
  name: string;
  private: boolean;
  default_branch: string;
  description: string | null;
  html_url: string;
  install_id: number | null;
}

export interface ConnectRepoRequest {
  install_id?: number | null;
  repo_id: number;
  repo_full_name: string;
  default_branch: string;
}

/* Quotas */
export interface Quota {
  id: string;
  project_id: string;
  cpu_limit: number;
  ram_limit: number;
  disk_limit: number;
}

export interface QuotaWithProject {
  id: string;
  project_id: string;
  project_name: string;
  project_slug: string;
  owner_username: string;
  cpu_limit: number;
  ram_limit: number;
  disk_limit: number;
}

export interface QuotaUpdate {
  cpu_limit?: number;
  ram_limit?: number;
  disk_limit?: number;
}

export interface QuotaListResponse {
  items: QuotaWithProject[];
  total: number;
}

/* User management (admin) */
export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string;
  role: string;
  github_username: string | null;
  project_count: number;
  created_at: string;
}

export interface AdminUserListResponse {
  items: AdminUser[];
  total: number;
}

export interface UserRoleUpdate {
  role: "JAS_Developer" | "JAS-Staff" | "JAS-Faculty";
}

/* Network policies */
export interface NetworkPolicy {
  id: string;
  project_id: string;
  project_name: string | null;
  name: string;
  direction: "egress" | "ingress";
  protocol: "tcp" | "udp" | "icmp" | "any";
  port: number | null;
  destination: string;
  action: "allow" | "deny";
  enabled: boolean;
  created_at: string;
}

export interface NetworkPolicyCreate {
  project_id: string;
  name: string;
  direction?: "egress" | "ingress";
  protocol?: "tcp" | "udp" | "icmp" | "any";
  port?: number | null;
  destination: string;
  action?: "allow" | "deny";
}

export interface NetworkPolicyUpdate {
  name?: string;
  protocol?: "tcp" | "udp" | "icmp" | "any";
  port?: number | null;
  destination?: string;
  action?: "allow" | "deny";
  enabled?: boolean;
}

export interface NetworkPolicyListResponse {
  items: NetworkPolicy[];
  total: number;
}

/* Admin dashboard stats */
export interface AdminStats {
  total_users: number;
  total_projects: number;
  total_deploys: number;
  active_deploys: number;
  total_builds: number;
  vlans_allocated: number;
  vlans_available: number;
  total_network_policies: number;
}

/* Templates */
export interface Template {
  id: string;
  name: string;
  slug: string;
  description: string;
  framework: string;
  github_owner: string;
  github_repo: string;
  icon_url: string | null;
  tags: string[];
  sort_order: number;
  active: boolean;
  created_at: string;
}

export interface TemplateListResponse {
  items: Template[];
  total: number;
}

export interface TemplateDeployRequest {
  repo_name: string;
  description?: string;
  private?: boolean;
}

export interface TemplateDeployResponse {
  project_id: string;
  project_slug: string;
  repo_full_name: string;
  repo_html_url: string;
  build_id: string | null;
  message: string;
}
