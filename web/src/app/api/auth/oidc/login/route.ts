import { NextResponse } from "next/server";
import { authorizeEndpoint, createPkcePair, requestOrigin, ssoConfigured } from "@/lib/sso";

export const dynamic = "force-dynamic";

const FLOW_COOKIE_OPTIONS = {
  httpOnly: true,
  sameSite: "lax" as const,
  path: "/",
  maxAge: 600,
  secure: process.env.NODE_ENV === "production",
};

/** Start the auth-service SSO flow: build an authorization-code + PKCE
 *  request and stash flow state in short-lived httpOnly cookies. */
export async function GET(req: Request) {
  const url = requestOrigin(req);
  const redirectParam = url.searchParams.get("redirect") ?? "/dashboard";
  const redirect = redirectParam.startsWith("/") ? redirectParam : "/dashboard";

  if (!ssoConfigured()) {
    return NextResponse.redirect(new URL("/login?sso_error=not_configured", url.origin));
  }

  const state = crypto.randomUUID();
  const nonce = crypto.randomUUID();
  const { verifier, challenge } = await createPkcePair();

  const params = new URLSearchParams({
    response_type: "code",
    client_id: process.env.OIDC_CLIENT_ID ?? "",
    redirect_uri: `${url.origin}/api/auth/oidc/callback`,
    scope: "openid email profile amr groups",
    state,
    nonce,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });

  const res = NextResponse.redirect(`${await authorizeEndpoint()}?${params.toString()}`);
  res.cookies.set("oidc_state", state, FLOW_COOKIE_OPTIONS);
  res.cookies.set("oidc_verifier", verifier, FLOW_COOKIE_OPTIONS);
  res.cookies.set("oidc_nonce", nonce, FLOW_COOKIE_OPTIONS);
  res.cookies.set("oidc_redirect", redirect, FLOW_COOKIE_OPTIONS);
  return res;
}
