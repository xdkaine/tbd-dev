import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  decodeIdTokenClaims,
  exchangeCode,
  internalApiBase,
  requestOrigin,
  ssoConfigured,
} from "@/lib/sso";

export const dynamic = "force-dynamic";

const FLOW_COOKIES = ["oidc_state", "oidc_verifier", "oidc_nonce", "oidc_redirect"] as const;

/** SSO callback: validate state/nonce, exchange the code at the provider,
 *  then swap the ID token for a platform session JWT via the API. The
 *  session token is handed to a client bridge page through the URL fragment
 *  (fragments are never sent to the server) which stores it in localStorage —
 *  the same session contract as the classic login form. */
export async function GET(req: Request) {
  const url = requestOrigin(req);

  const fail = (reason: string) => {
    const res = NextResponse.redirect(
      new URL(`/login?sso_error=${encodeURIComponent(reason)}`, url.origin),
    );
    for (const name of FLOW_COOKIES) {
      res.cookies.set(name, "", { path: "/", maxAge: 0 });
    }
    return res;
  };

  if (!ssoConfigured()) return fail("not_configured");

  const error = url.searchParams.get("error");
  if (error) return fail(error);

  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const jar = cookies();
  const expectedState = jar.get("oidc_state")?.value;

  if (!code || !state) return fail("invalid_callback");
  if (!expectedState) return fail("missing_flow_cookie");
  if (state !== expectedState) {
    return fail("state_mismatch");
  }

  const verifier = jar.get("oidc_verifier")?.value ?? "";
  const nonce = jar.get("oidc_nonce")?.value ?? "";
  const redirect = jar.get("oidc_redirect")?.value || "/dashboard";

  if (!verifier || !nonce) return fail("missing_flow_cookie");

  let tokens;
  try {
    tokens = await exchangeCode({
      code,
      redirectUri: `${url.origin}/api/auth/oidc/callback`,
      verifier,
    });
  } catch {
    return fail("token_exchange_failed");
  }

  const idToken = tokens.id_token;
  if (!idToken) return fail("missing_id_token");

  // Nonce binding check (signature + iss/aud/exp are verified by the API)
  const claims = decodeIdTokenClaims(idToken);
  if (!claims) return fail("bad_id_token");
  if (nonce && claims.nonce !== nonce) return fail("nonce_mismatch");

  let accessToken: string | undefined;
  try {
    const res = await fetch(`${internalApiBase()}/auth/oidc/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken, access_token: tokens.access_token }),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      console.error("OIDC exchange rejected by API:", res.status);
      return fail("exchange_rejected");
    }
    const data = (await res.json()) as { access_token?: string };
    accessToken = data.access_token;
  } catch (err) {
    console.error("OIDC exchange request failed:", err);
    return fail("exchange_failed");
  }

  if (!accessToken) return fail("no_session_token");

  const bridge = new URL("/auth/sso-bridge", url.origin);
  bridge.hash = `token=${encodeURIComponent(accessToken)}&redirect=${encodeURIComponent(redirect)}`;

  const res = NextResponse.redirect(bridge);
  for (const name of FLOW_COOKIES) {
    res.cookies.set(name, "", { path: "/", maxAge: 0 });
  }
  return res;
}
