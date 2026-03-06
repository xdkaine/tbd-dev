import clsx from "clsx";
import type { DeployStatus } from "@/lib/types";

/**
 * Deploy state machine steps in order (from docs/deploy-state-machine.md).
 * Visual pipeline showing each state as a step with connection lines.
 */

const PIPELINE_STEPS: DeployStatus[] = [
  "queued",
  "building",
  "artifact_ready",
  "provisioning",
  "healthy",
  "active",
];

const TERMINAL_STATES: DeployStatus[] = ["failed", "rolled_back", "superseded", "stopped"];

const STEP_LABELS: Record<DeployStatus, string> = {
  queued: "Queued",
  building: "Building",
  artifact_ready: "Artifact Ready",
  provisioning: "Provisioning",
  healthy: "Healthy",
  active: "Active",
  failed: "Failed",
  rolled_back: "Rolled Back",
  superseded: "Superseded",
  stopped: "Stopped",
};

function getStepState(
  step: DeployStatus,
  currentStatus: DeployStatus,
): "completed" | "current" | "pending" | "failed" {
  if (TERMINAL_STATES.includes(currentStatus)) {
    // If failed/rolled_back/superseded, find the last completed step
    const currentIdx = PIPELINE_STEPS.indexOf(currentStatus);
    if (currentIdx === -1) {
      // Terminal state: mark everything up to where we were as completed
      // We don't know exact point, so just show the terminal badge
      if (step === currentStatus) return "failed";
      return "pending";
    }
  }

  const stepIdx = PIPELINE_STEPS.indexOf(step);
  const currentIdx = PIPELINE_STEPS.indexOf(currentStatus);

  if (currentIdx === -1) {
    // Current status is terminal (failed, etc.)
    return "pending";
  }

  if (stepIdx < currentIdx) return "completed";
  if (stepIdx === currentIdx) return "current";
  return "pending";
}

export function DeployPipeline({ status }: { status: DeployStatus }) {
  const isTerminal = TERMINAL_STATES.includes(status);

  return (
    <div>
      {/* Main pipeline */}
      <div className="flex items-center gap-1">
        {PIPELINE_STEPS.map((step, i) => {
          const state = getStepState(step, status);
          return (
            <div key={step} className="flex items-center">
              {/* Step circle + label */}
              <div className="flex flex-col items-center">
                <div
                  className={clsx(
                    "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-bold",
                    state === "completed" &&
                      "border-green-500 bg-green-950/30 text-green-400",
                    state === "current" &&
                      "border-brand-500 bg-brand-950/50 text-brand-400 ring-2 ring-brand-800",
                    state === "pending" &&
                      "border-zinc-700 bg-zinc-800/50 text-zinc-500",
                    state === "failed" &&
                      "border-red-500 bg-red-950/30 text-red-400",
                  )}
                >
                  {state === "completed" ? (
                    <CheckIcon />
                  ) : (
                    i + 1
                  )}
                </div>
                <span
                  className={clsx(
                    "mt-1 text-[10px] font-medium leading-tight",
                    state === "completed" && "text-green-400",
                    state === "current" && "text-brand-400",
                    state === "pending" && "text-zinc-500",
                    state === "failed" && "text-red-400",
                  )}
                >
                  {STEP_LABELS[step]}
                </span>
              </div>

              {/* Connector line */}
              {i < PIPELINE_STEPS.length - 1 && (
                <div
                  className={clsx(
                    "mx-1 h-0.5 w-6",
                    getStepState(PIPELINE_STEPS[i + 1], status) !== "pending"
                      ? "bg-green-400"
                      : "border-zinc-700 bg-zinc-700",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Terminal state badge (if applicable) */}
      {isTerminal && (
        <div className="mt-3">
          <span
            className={clsx(
              "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold",
              status === "failed" && "bg-red-950/30 text-red-400",
              status === "rolled_back" && "bg-orange-950/30 text-orange-400",
              status === "superseded" && "bg-zinc-800 text-zinc-500",
              status === "stopped" && "bg-amber-950/30 text-amber-400",
            )}
          >
            {STEP_LABELS[status]}
          </span>
        </div>
      )}
    </div>
  );
}

function CheckIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={3}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}
