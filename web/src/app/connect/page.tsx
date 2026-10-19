"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {useNativeGallery} from '@/components/native/gallery-controls';
import {api} from '@/lib/api';
const field='w-full h-12 rounded-xl bg-background px-3';
export default function Connect(){
 const native=useNativeGallery();
 const [dateEdited,setDateEdited]=useState(false);
 const [email,setEmail]=useState('');const [password,setPassword]=useState('');
 const [signed,setSigned]=useState(false);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [processing,setProcessing]=useState(false);const [automatic,setAutomatic]=useState(false);
 const [date,setDate]=useState(new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Bangkok'}));
 useEffect(()=>{fetch('/api/session',{cache:'no-store'}).then(r=>{if(r.ok)setSigned(true)}).catch(()=>{});},[]);
 useEffect(()=>{if(native && !dateEdited){const day=new Date(Date.now()-30*24*60*60*1000);setDate(day.toLocaleDateString('en-CA',{timeZone:'Asia/Bangkok'}));}},[!!native,dateEdited]);
 async function auth(action:string){setBusy(true);setError('');try{
 const r=await fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,email,password})});const d=await r.json();if(!r.ok)throw new Error(d.error?.message??'Sign in failed');setSigned(true);
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function consent(){setBusy(true);setError('');try{
 if(processing)await api('/consents',{method:'POST',body:JSON.stringify({scope:'photo_processing',version:'web-v1',params:{scan_from:date}})});
 if(automatic){if(!processing)throw new Error('Allow photo processing before automatic import.');await api('/consents',{method:'POST',body:JSON.stringify({scope:'auto_import',version:'web-v1',params:{}})});}
 window.location.assign('/');
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <main className="mx-auto max-w-[430px] min-h-dvh bg-background p-[18px]"><section className="rounded-[24px] bg-card p-5 space-y-4 shadow-[var(--shadow-card)]"><h1 className="text-2xl font-extrabold">Pocket Pal</h1><p>{signed?'Choose how your photos are processed':'Sign in to your account'}</p>
 {!signed?<><label className="block">Email<input className={field} type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)}/></label><label className="block">Password<input className={field} type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><div className="flex gap-3"><button className="rounded-xl bg-ink text-white p-3" disabled={busy} onClick={()=>auth('login')}>Sign in</button><button disabled={busy} onClick={()=>auth('signup')}>Create account</button></div></>:<><p className="text-sm">When real extraction is enabled, selected photos are sent to Anthropic. Browser access sends only photos you choose. The Android app can scan likely slips in the last 30 days only after you enable Gallery scanning in Settings.</p><label className="block"><input type="checkbox" checked={processing} onChange={e=>setProcessing(e.target.checked)}/> Allow photo processing</label><label className="block">Photos from<input type="date" className={field} value={date} onChange={e=>{setDate(e.target.value);setDateEdited(true)}}/></label><label className="block"><input type="checkbox" checked={automatic} onChange={e=>setAutomatic(e.target.checked)}/> Automatically import readable transactions</label><button className="rounded-xl bg-ink p-3 text-white" disabled={busy} onClick={consent}>Continue</button><Link className="block" href="/welcome">Set up balance and income</Link><Link className="block" href="/">Back to Chat</Link></>}
 {error&&<p role="alert" className="text-danger">{error}</p>}</section></main>
}
