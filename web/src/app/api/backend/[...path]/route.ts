import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, failure, sameOrigin, upstream } from "@/lib/backend-server";
export const runtime = "nodejs";
const LIMIT = 9 * 1024 * 1024;
async function handle(req: NextRequest, ctx: { params: Promise<{path: string[]}> }) {
  if (!sameOrigin(req)) return failure(403,"ORIGIN_MISMATCH","Request origin is not allowed.");
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return failure(401,"UNAUTHENTICATED","Please sign in.");
  const {path} = await ctx.params;
  if (!path.length || path.some(p => !/^[a-zA-Z0-9_-]+$/.test(p)) || path[0] === "auth") return failure(400,"INVALID_PATH","Invalid API path.");
  if (Number(req.headers.get("content-length") ?? 0) > LIMIT) return failure(413,"UPLOAD_TOO_LARGE","Request is too large.");
  try {
    const headers = new Headers({Authorization:`Bearer ${token}`});
    for (const k of ["content-type","idempotency-key"]) { const v=req.headers.get(k);if(v) headers.set(k,v); }
    let body: ArrayBuffer | undefined;
    if (!["GET","HEAD"].includes(req.method)) {
      // Bound streaming reads, including clients without Content-Length.
      const reader=req.body?.getReader(); const chunks: Uint8Array[]=[];let size=0;
      if(reader) { while(true) { const {done,value}=await reader.read();if(done)break;size+=value.length;
        if(size>LIMIT){await reader.cancel();return failure(413,"UPLOAD_TOO_LARGE","Request is too large.");} chunks.push(value); }
      }
      const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}body=bytes.buffer;
    }
    const res=await upstream(path.join("/")+req.nextUrl.search,{method:req.method,headers,body});
    const outHeaders=new Headers({"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff"});
    for(const k of ["content-type","x-request-id"]) {const v=res.headers.get(k);if(v)outHeaders.set(k,v);}
    return new NextResponse(res.status===204?null:res.body,{status:res.status,headers:outHeaders});
  } catch {return failure(502,"BACKEND_UNAVAILABLE","The server did not answer. Check status before retrying a change.");}
}
export const GET=handle;export const POST=handle;export const PUT=handle;export const PATCH=handle;export const DELETE=handle;
