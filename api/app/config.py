"""TBD Platform - Control Plane API configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://tbd:tbd_dev_password@localhost:5432/tbd"

    # Active Directory / LDAP
    ad_ldap_url: str = "ldap://localhost:389"
    ad_base_dn: str = "DC=example,DC=com"
    ad_bind_dn: str = "CN=svc-tbd,OU=Service Accounts,DC=example,DC=com"
    ad_bind_password: str = ""
    ad_user_search_base: str = ""  # Defaults to ad_base_dn if empty
    ad_group_search_base: str = ""  # Defaults to ad_base_dn if empty

    # AD Group-to-Role Mapping
    ad_developer_group: str = "JAS_Developer"
    ad_staff_group: str = "JAS-Staff"
    ad_faculty_group: str = "JAS-Faculty"

    # JWT / Auth
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # Registry
    registry_url: str = "http://localhost:5000"
    registry_ip: str = ""  # IP for firewall allow-list
    registry_username: str = ""  # Registry basic auth username
    registry_password: str = ""  # Registry basic auth password

    # GitHub App
    github_app_id: str = ""
    github_app_private_key: str = ""  # PEM-encoded RSA private key (newlines as \n)
    github_webhook_secret: str = ""  # Webhook signing secret

    # GitHub OAuth (user account linking)
    github_client_id: str = ""
    github_client_secret: str = ""

    # Deploy queue
    deploy_max_concurrent: int = 2  # Max concurrent deploys per environment
    deploy_queue_max_size: int = 50  # Max queued deploys per environment

    # Build limits
    build_max_concurrent: int = 4  # Max simultaneous builds (docker build + push)
    build_timeout_seconds: int = 600  # Hard timeout per build (10 minutes)

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Rate limiting
    rate_limit_rpm: int = 120  # Requests per minute per IP (global)
    rate_limit_auth_rpm: int = 10  # Requests per minute per IP (auth/login)

    # SSE stream limits
    sse_stream_timeout_seconds: int = 600  # Max SSE stream duration (10 minutes)

    # Secrets encryption
    secrets_encryption_key: str = ""  # Fernet key, generated if empty

    # Aggregate quota limits per user (0 = no limit)
    user_max_cpu: int = 0  # Max total vCPUs across all projects (0 = unlimited)
    user_max_ram_mb: int = 0  # Max total RAM in MB across all projects (0 = unlimited)
    user_max_disk_mb: int = 0  # Max total disk in MB across all projects (0 = unlimited)
    user_max_projects: int = 0  # Max projects per user (0 = unlimited)

    # Proxmox
    proxmox_api_url: str = "https://localhost:8006"  # Proxmox VE API base URL
    proxmox_verify_ssl: bool = False  # Verify SSL for Proxmox API
    proxmox_token_id: str = ""  # PVEAPIToken user@realm!tokenid
    proxmox_token_secret: str = ""  # PVEAPIToken UUID secret
    proxmox_storage: str = "local-lvm"  # Storage backend for LXC rootfs volumes
    proxmox_template_storage: str = "local"  # Storage for uploaded CT templates (vztmpl)
    proxmox_pool: str = ""  # Proxmox resource pool for LXC containers (e.g. "TBD_Project")
    proxmox_bridge: str = "vmbr0"  # Network bridge for LXC containers (e.g. "Critical")

    # Flat IP allocation (temporary — bypasses VLAN system)
    # When set, deploy_executor uses this range instead of VLAN-based IPs.
    deploy_ip_start: str = ""  # First IP in range (e.g. "10.128.30.80")
    deploy_ip_end: str = ""  # Last IP in range (e.g. "10.128.30.100")
    deploy_gateway: str = ""  # Gateway for flat IP range (e.g. "10.128.30.1")
    deploy_subnet_bits: int = 24  # Subnet mask bits (e.g. 24 for /24)

    # OCI conversion work directory
    oci_work_dir: str = "/var/lib/tbd/oci"  # Root directory for skopeo/umoci work

    # Domain scheme
    # Base domain suffix for deploy URLs: <deployid>-<username>.<deploy_domain_suffix>
    deploy_domain_suffix: str = "dev.sdc.cpp"

    @property
    def ui_domain(self) -> str:
        """Platform UI domain (root of deploy_domain_suffix)."""
        return self.deploy_domain_suffix

    @property
    def api_domain(self) -> str:
        """Platform API domain."""
        return f"api.{self.deploy_domain_suffix}"

    @property
    def registry_domain(self) -> str:
        """OCI registry domain."""
        return f"registry.{self.deploy_domain_suffix}"

    # Networking
    nginx_upstream_dir: str = "/etc/nginx/conf.d/upstreams"  # Nginx upstream config directory
    nginx_reload_flag_dir: str = "/var/run/nginx-reload"  # Shared dir for nginx reload signaling
    nginx_ingress_ip: str = ""  # Nginx ingress IP for firewall allow-list
    platform_api_ip: str = ""  # Platform API IP for firewall allow-list
    nfs_server_ip: str = ""  # NFS server IP for firewall allow-list
    internal_dns_ip: str = ""  # Internal DNS IP for firewall allow-list

    @property
    def user_search_base(self) -> str:
        return self.ad_user_search_base or self.ad_base_dn

    @property
    def group_search_base(self) -> str:
        return self.ad_group_search_base or self.ad_base_dn

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
