import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

export async function GET() {
  const releaseProbe = (await readFile(path.join(process.cwd(), "public", "release-probe.txt"), "utf8")).trim();
  return Response.json({ service: "tbd-web", revision: process.env.APP_REVISION ?? "development", releaseProbe }, { headers: { "Cache-Control": "no-store" } });
}
