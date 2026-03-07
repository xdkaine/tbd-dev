"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/auth";
import { useEffect } from "react";
import clsx from "clsx";

/* ------------------------------------------------------------------ */
/*  Navigation item definitions — one set per role                    */
/* ------------------------------------------------------------------ */

interface NavItem {
  href: string;
  label: string;
  roles: string[];
  exact?: boolean;
  section?: string;
  indent?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  // ---- Developer items ----
  { href: "/dashboard", label: "Projects", roles: ["JAS_Developer", "JAS-Staff", "JAS-Faculty"] },
  { href: "/settings", label: "Settings", roles: ["JAS_Developer", "JAS-Staff", "JAS-Faculty"] },

  // ---- Staff section ----
  { href: "/staff", label: "Overview", roles: ["JAS-Staff"], exact: true, section: "staff" },
  { href: "/staff/projects", label: "All Projects", roles: ["JAS-Staff"], indent: true },
  { href: "/staff/students", label: "Students", roles: ["JAS-Staff"], indent: true },
  { href: "/staff/tags", label: "Tags", roles: ["JAS-Staff"], indent: true },
  { href: "/staff/quotas", label: "Quotas", roles: ["JAS-Staff"], indent: true },
  { href: "/staff/vlans", label: "VLANs", roles: ["JAS-Staff"], indent: true },
  { href: "/staff/audit", label: "Audit Log", roles: ["JAS-Staff"], indent: true },

  // ---- Faculty section ----
  { href: "/faculty", label: "Overview", roles: ["JAS-Faculty"], exact: true, section: "faculty" },
  { href: "/faculty/projects", label: "All Projects", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/students", label: "Students", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/tags", label: "Tags", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/users", label: "Users", roles: ["JAS-Faculty"], indent: true, section: "management" },
  { href: "/faculty/quotas", label: "Quotas", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/network-policies", label: "Network Policies", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/vlans", label: "VLANs", roles: ["JAS-Faculty"], indent: true },
  { href: "/faculty/audit", label: "Audit Log", roles: ["JAS-Faculty"], indent: true },

  // ---- Legacy admin section (kept active, accessible to both) ----
  { href: "/admin", label: "Admin", roles: ["JAS-Staff", "JAS-Faculty"], exact: true, section: "admin" },
  { href: "/admin/users", label: "Users", roles: ["JAS-Staff", "JAS-Faculty"], indent: true },
  { href: "/admin/quotas", label: "Quotas", roles: ["JAS-Staff", "JAS-Faculty"], indent: true },
  { href: "/admin/network-policies", label: "Network Policies", roles: ["JAS-Staff", "JAS-Faculty"], indent: true },
  { href: "/admin/vlans", label: "VLANs", roles: ["JAS-Staff", "JAS-Faculty"], indent: true },
  { href: "/admin/audit", label: "Audit Log", roles: ["JAS-Staff", "JAS-Faculty"], indent: true },
];

interface SidebarProps {
  /** Mobile-only: whether the sidebar drawer is open */
  mobileOpen?: boolean;
  /** Mobile-only: callback to close the drawer */
  onMobileClose?: () => void;
}

/** Sidebar content shared between desktop and mobile */
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  if (!user) return null;

  const visibleItems = NAV_ITEMS.filter((item) =>
    item.roles.includes(user.role),
  );

  return (
    <>
      {/* Brand */}
      <div className="flex h-14 items-center border-b border-zinc-800 px-4">
        <Link
          href="/dashboard"
          className="font-mono text-lg font-bold text-brand-500"
          onClick={onNavigate}
        >
          tbd
        </Link>
        <span className="ml-2 rounded bg-brand-950 px-1.5 py-0.5 text-[10px] font-semibold text-brand-400 uppercase">
          {user.role}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {visibleItems.map((item) => {
          const isActive = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href);

          return (
            <div key={item.href}>
              {item.section && (
                <div className="mb-1 mt-4 border-t border-zinc-800 pt-3">
                  <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
                    {item.section === "staff" ? "Staff" :
                     item.section === "faculty" ? "Faculty" :
                     item.section === "management" ? "Management" :
                     "Admin"}
                  </p>
                </div>
              )}
              <Link
                href={item.href}
                onClick={onNavigate}
                className={clsx(
                  "block rounded-md py-1.5 text-sm font-medium transition-colors",
                  item.indent ? "pl-6 pr-3" : "px-3",
                  isActive
                    ? "bg-brand-500/10 text-brand-400"
                    : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200",
                )}
              >
                {item.label}
              </Link>
            </div>
          );
        })}
      </nav>

      {/* User footer */}
      <div className="border-t border-zinc-800 p-3">
        <p className="truncate text-sm font-medium text-zinc-200">
          {user.display_name}
        </p>
        <p className="truncate text-xs text-zinc-500">{user.email}</p>
        <button
          onClick={logout}
          className="mt-2 text-xs text-red-400 hover:text-red-300 transition-colors"
        >
          Sign out
        </button>
      </div>
    </>
  );
}

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();

  // Close mobile drawer on route change
  useEffect(() => {
    onMobileClose?.();
  }, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {/* Desktop sidebar — always visible at md+ */}
      <aside className="hidden md:flex h-screen w-56 flex-col border-r border-zinc-800 bg-[#0a0a0c]">
        <SidebarContent />
      </aside>

      {/* Mobile sidebar — overlay drawer */}
      <div
        className={clsx(
          "fixed inset-0 z-40 md:hidden transition-opacity duration-200",
          mobileOpen ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
      >
        {/* Backdrop */}
        <div
          className="absolute inset-0 bg-black/60"
          onClick={onMobileClose}
          aria-hidden="true"
        />

        {/* Drawer panel */}
        <aside
          className={clsx(
            "relative flex h-full w-64 max-w-[80vw] flex-col bg-[#0a0a0c] shadow-xl",
            "transition-transform duration-200 ease-in-out",
            mobileOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          {/* Close button */}
          <button
            onClick={onMobileClose}
            className="absolute top-3 right-3 rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
            aria-label="Close sidebar"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>

          <SidebarContent onNavigate={onMobileClose} />
        </aside>
      </div>
    </>
  );
}
