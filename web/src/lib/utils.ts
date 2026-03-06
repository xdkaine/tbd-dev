/** Utility for formatting dates. */
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Relative time (e.g. "2 minutes ago"). */
export function timeAgo(iso: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(iso).getTime()) / 1000,
  );
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Slug-ify a project name. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Bucket deploy activity by day. */
export function getDeployActivity<T extends { created_at: string }>(
  deploys: T[],
  days: number = 7,
): { date: string; count: number }[] {
  const now = new Date();
  const buckets: { date: string; count: number }[] = [];
  const bucketMap: Record<string, { date: string; count: number }> = {};

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const bucket = { date: dateStr, count: 0 };
    buckets.push(bucket);
    bucketMap[dateStr] = bucket;
  }

  for (const deploy of deploys) {
    const deployDate = deploy.created_at.slice(0, 10);
    const bucket = bucketMap[deployDate];
    if (bucket) bucket.count++;
  }

  return buckets;
}
