import { NextRequest, NextResponse } from "next/server";
export const SESSION_COOKIE = "pocket_pal_session";
export function backendBase(): string {
  const url = new URL(process.env.FINASSIST_BACKEND_URL ?? "http://127.0.0.1:8000");
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error("Invalid backend origin");
  if (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname))) throw new Error("Backend must use HTTPS or loopback HTTP");
  return url.origin;
}
export function failure(status: number, code: string, message: string) {
  return NextResponse.json({error:{code,message}}, {status,headers:{"Cache-Control":"no-store"}});
}
export function sameOrigin(req: NextRequest): boolean {
  if (["GET", "HEAD"].includes(req.method)) return true;
  // Next's standalone request URL may use its bind hostname rather than the
  // browser's Host (localhost on the USB-forwarded phone).
  const origin = req.headers.get("origin");
  if (!origin) return false;
  try {
    const parsed = new URL(origin);
    return parsed.origin === origin && parsed.host === req.headers.get("host")
      && parsed.protocol === req.nextUrl.protocol;
  } catch { return false; }
}
export async function upstream(path: string, init: RequestInit = {}) {
  return fetch(`${backendBase()}/v1/${path}`, {...init,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(120000)});
}
