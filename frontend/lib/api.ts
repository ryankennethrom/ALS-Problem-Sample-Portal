import { toastError, toastSuccess } from '@/lib/toast';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export function getToken(){ if(typeof window==='undefined') return null; return sessionStorage.getItem('pst_token'); }
export function setToken(token:string){ sessionStorage.setItem('pst_token',token); }
export function clearToken(){ sessionStorage.removeItem('pst_token'); }

type ApiInit = RequestInit & {
  successMessage?: string;
  errorMessage?: string;
};

function operationError(prefix: string | undefined, detail: string) {
  if (!prefix) return;
  toastError(detail && detail !== prefix ? `${prefix}: ${detail}` : prefix);
}

export async function api(path:string, init:ApiInit={}){
  const { successMessage, errorMessage, ...requestInit } = init;
  const headers = new Headers(requestInit.headers || {});
  if(!(requestInit.body instanceof FormData)) headers.set('Content-Type','application/json');
  const token=getToken(); if(token) headers.set('Authorization',`Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API}${path}`,{...requestInit,headers,cache:'no-store'});
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network request failed';
    operationError(errorMessage, message);
    throw error;
  }

  if(!res.ok){
    let msg=`Request failed (${res.status})`;
    try{
      const d=await res.json();
      msg=d.detail || d.error || (typeof d === 'string' ? d : JSON.stringify(d));
    }catch{}
    operationError(errorMessage, msg);
    throw new Error(msg);
  }

  if(successMessage) toastSuccess(successMessage);
  if(res.status===204) return null;
  return res.json();
}


export async function apiBlob(path:string, init:ApiInit={}){
  const { successMessage, errorMessage, ...requestInit } = init;
  const headers = new Headers(requestInit.headers || {});
  if(!(requestInit.body instanceof FormData)) headers.set('Content-Type','application/json');
  const token=getToken(); if(token) headers.set('Authorization',`Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API}${path}`,{...requestInit,headers,cache:'no-store'});
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network request failed';
    operationError(errorMessage, message);
    throw error;
  }
  if(!res.ok){
    let msg=`Request failed (${res.status})`;
    try{
      const d=await res.json();
      msg=d.detail || d.error || (typeof d === 'string' ? d : JSON.stringify(d));
    }catch{}
    operationError(errorMessage, msg);
    throw new Error(msg);
  }
  if(successMessage) toastSuccess(successMessage);
  return res.blob();
}
