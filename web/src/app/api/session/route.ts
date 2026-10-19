import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, failure, sameOrigin, upstream } from "@/lib/backend-server";
export const runtime="nodejs";
export async function GET(req:NextRequest) {
  const token=req.cookies.get(SESSION_COOKIE)?.value;
  if(!token)return failure(401,"UNAUTHENTICATED","Please sign in.");
  try {
    const me=await upstream("me",{headers:{Authorization:`Bearer ${token}`}});
    if(!me.ok)return failure(me.status,"IDENTITY_UNAVAILABLE","Your session could not be confirmed.");
    const identity=await me.json();
    const health=await upstream("health");
    if(!health.ok)return failure(503,"HEALTH_UNAVAILABLE","The server status could not be confirmed.");
    return NextResponse.json({...identity,test_mode:(await health.json()).test_mode},{headers:{"Cache-Control":"no-store"}});
  } catch {return failure(502,"BACKEND_UNAVAILABLE","Cannot reach the server. Retry when it is available.");}
}
export async function POST(req:NextRequest) {
  if(!sameOrigin(req))return failure(403,"ORIGIN_MISMATCH","Request origin is not allowed.");
  if(Number(req.headers.get("content-length")??0)>4096)return failure(413,"TOO_LARGE","Request too large.");
  try {
    const reader=req.body?.getReader();const chunks:Uint8Array[]=[];let size=0;
    if(reader)while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>4096){await reader.cancel();return failure(413,"TOO_LARGE","Request too large.");}chunks.push(value);}
    const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
    let parsed;try{parsed=JSON.parse(new TextDecoder().decode(bytes));}catch{return failure(400,"INVALID_INPUT","Enter email and password.");}
    if(!parsed || typeof parsed!=="object")return failure(400,"INVALID_INPUT","Enter email and password.");
    const {action,email,password}=parsed;
    if(action==="logout") {
      const token=req.cookies.get(SESSION_COOKIE)?.value;
      if(token) await upstream("auth/logout",{method:"POST",headers:{Authorization:`Bearer ${token}`}}).catch(()=>null);
      const res=NextResponse.json({signed_out:true});res.cookies.delete(SESSION_COOKIE);return res;
    }
    if(!["login","signup"].includes(action)||typeof email!=="string"||typeof password!=="string")return failure(400,"INVALID_INPUT","Enter email and password.");
    if(action==="signup") {
      const sign=await upstream("auth/signup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
      if(!sign.ok)return new NextResponse(sign.body,{status:sign.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
    }
    const login=await upstream("auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
    const data=await login.json();
    if(!login.ok)return NextResponse.json(data,{status:login.status,headers:{"Cache-Control":"no-store"}});
    const res=NextResponse.json({signed_in:true},{headers:{"Cache-Control":"no-store"}});
    res.cookies.set(SESSION_COOKIE,data.token,{httpOnly:true,sameSite:"strict",secure:req.nextUrl.protocol==="https:",path:"/"});
    return res;
  } catch {return failure(502,"BACKEND_UNAVAILABLE","Could not complete sign in. Please check the server.");}
}
