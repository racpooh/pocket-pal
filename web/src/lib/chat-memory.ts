"use client";
import { useSyncExternalStore } from "react";
import type { ServerProposal } from "@/components/action-card/server-action-card";
export type ChatEntry = { id:string; role:"user"|"assistant"|"status"|"proposal"; text?:string; proposal?:ServerProposal };
type Memory = {owner:string|null; epoch:number; entries:ChatEntry[]; draft:string; sending:boolean};
const empty:Memory={owner:null,epoch:0,entries:[],draft:"",sending:false};
let state:Memory=empty;
const listeners=new Set<()=>void>();
function publish(next:Memory){state=next;listeners.forEach(f=>f());}
export function clearChatMemory(){publish({...empty,epoch:state.epoch+1});}
export function bindChatOwner(owner:string){if(state.owner!==owner)publish({...empty,owner,epoch:state.epoch+1});return state.epoch;}
export function currentChat(){return state;}
export function changeChat(owner:string,epoch:number,patch:Partial<Memory>){if(state.owner===owner&&state.epoch===epoch)publish({...state,...patch});}
export function restartChat(owner:string){publish({...empty,owner,epoch:state.epoch+1});}
export function useChatMemory(){return useSyncExternalStore((f)=>{listeners.add(f);return()=>{listeners.delete(f);};},()=>state,()=>empty);}
