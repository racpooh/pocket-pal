"use client";
import { useEffect,useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { bindChatOwner, clearChatMemory } from "@/lib/chat-memory";
export function SessionBoundary({children}:{children:React.ReactNode}) {
  const path=usePathname();
  const [state,setState]=useState<{owner?:string;test?:boolean;error?:string;path?:string}>({});
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let live=true;setState({});
    if(path==="/connect"){clearChatMemory();return;}
    fetch('/api/session',{cache:'no-store'}).then(async r=>{const d=await r.json();
      if(!r.ok)throw new Error(d.error?.message??'Please sign in.');
      if(live){bindChatOwner(d.user_id);setState({owner:d.user_id,test:d.test_mode,path});}
    }).catch(e=>{if(live){clearChatMemory();setState({error:e.message});}});
    return()=>{live=false};
  },[path,attempt]);
  if(path==="/connect")return children;
  if(!state.owner || state.path!==path)return <main className="mx-auto max-w-[430px] p-[18px] min-h-dvh bg-background"><section className="rounded-[24px] bg-card p-5 shadow-[var(--shadow-card)]"><h1 className="text-xl font-extrabold">Pocket Pal</h1><p role="status" className="my-4">{state.error??'Checking your account…'}</p>{state.error&&<div className="flex gap-4"><button onClick={()=>setAttempt(x=>x+1)}>Retry</button><Link href="/connect">Sign in</Link></div>}</section></main>;
  return <div key={state.owner}>{state.test&&<div className="mx-auto max-w-[430px] bg-amber-200 p-2 text-center text-xs font-bold">TEST MODE — synthetic fixtures, not real OCR</div>}{children}</div>;
}
