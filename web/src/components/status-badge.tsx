import clsx from "clsx";
import type { DeployStatus } from "@/lib/types";

const labels: Record<DeployStatus, string> = {
  queued: "Queued",
  building: "Building",
  artifact_ready: "Artifact Ready",
  provisioning: "Provisioning",
  healthy: "Healthy",
  active: "Active",
  stopped: "Stopped",
  failed: "Failed",
  rolled_back: "Rolled Back",
  superseded: "Active",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        `status-${status}`,
      )}
    >
      {labels[status as DeployStatus] ?? status}
    </span>
  );
}
