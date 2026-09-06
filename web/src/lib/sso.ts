/* ------------------------------------------------------------------ */
/*  Server-side OIDC (auth-service) helpers for the SSO login flow    */
/* ------------------------------------------------------------------ */

const ISSUER = (process.env.AUTH_ISSUER ?? "").replace(/\/+$/, "");
const CLIENT_ID = process.env.OIDC_CLIENT_ID ?? "";
const CLIENT_SECRET = process.env.OIDC_CLIENT_SECRET ?? "";

/** Absolute URL of the API reachable from the Next.js server process.
 *  Falls back to NEXT_PUBLIC_API_URL when it is absolute, else localhost:8000. */
export function internalApiBase(): string {
  const direct = process.env.API_INTERNAL_URL;
  if (direct) return direct.replace(/\/+$/, "");
  const pub = process.env.NEXT_PUBLIC_API_URL ?? "";
  if (/^https?:\/\//.test(pub)) return pub.replace(/\/+$/, "");
  return "http://localhost:8000";
}

/** Whether the auth-service SSO flow is fully configured. */
export function ssoConfigured(): boolean {
  return Boolean(ISSUER && CLIENT_ID && CLIENT_SECRET);
}

/** Public browser-facing origin for this deployment.
 *  Priority: SSO_PUBLIC_ORIGIN env → forwarded proto/host headers → internal
 *  req.url (which behind Nginx points at the container bind address). */
export function requestOrigin(req: Request): URL {
  const requestUrl = new URL(req.url);
  const requestPath = `${requestUrl.pathname}${requestUrl.search}`;
  const configured = process.env.SSO_PUBLIC_ORIGIN;
  if (configured) return new URL(requestPath, configured);
  const h = req.headers;
  const proto = h.get("x-forwarded-proto")?.split(",")[0]?.trim() ?? "";
  const host =
    h.get("x-forwarded-host")?.split(",")[0]?.trim() || h.get("host") || "";
  if (host && /^https?$/.test(proto)) {
    return new URL(requestPath, `${proto}://${host}`);
  }
  return requestUrl;
}

export interface PkcePair {
  verifier: string;
  challenge: string;
}

function b64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Create an S256 PKCE pair for the authorization request. */
export async function createPkcePair(): Promise<PkcePair> {
  const randoms = crypto.getRandomValues(new Uint8Array(32));
  const verifier = b64url(randoms.buffer);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return { verifier, challenge: b64url(digest) };
}

/** Resolve the provider's authorization endpoint via discovery. */
export async function authorizeEndpoint(): Promise<string> {
  try {
    const res = await fetch(`${ISSUER}/.well-known/openid-configuration`, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    if (res.ok) {
      const doc = (await res.json()) as { authorization_endpoint?: string };
      if (doc.authorization_endpoint) return doc.authorization_endpoint;
    }
  } catch {
    /* fall through to standard oidc-provider route */
  }
  return `${ISSUER}/auth`;
}

export interface OidcTokens {
  id_token?: string;
  access_token?: string;
}

/** Exchange an authorization code at the provider's token endpoint
 *  using client_secret_basic authentication and the PKCE verifier. */
export async function exchangeCode(params: {
  code: string;
  redirectUri: string;
  verifier: string;
}): Promise<OidcTokens> {
  const res = await fetch(`${ISSUER}/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString("base64")}`,
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code: params.code,
      redirect_uri: params.redirectUri,
      code_verifier: params.verifier,
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    throw new Error(`token exchange failed (${res.status})`);
  }
  return (await res.json()) as OidcTokens;
}

/** Decode (unverified) ID-token payload claims. Signature is verified by the API. */
export function decodeIdTokenClaims(idToken: string): Record<string, unknown> | null {
  try {
    const payloadB64 = idToken.split(".")[1];
    if (!payloadB64) return null;
    return JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
  } catch {
    return null;
  }
}
