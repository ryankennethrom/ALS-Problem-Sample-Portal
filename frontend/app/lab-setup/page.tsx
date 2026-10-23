'use client';
import {useEffect,useState} from 'react';
import {api, setActiveLabCode} from '@/lib/api';
export default function LabSetup(){
 const [labs,setLabs]=useState<Array<{id:number;name:string;code:string}>>([]);
 const [labId,setLabId]=useState('');const [error,setError]=useState('');
 useEffect(()=>{ api('/auth/labs/').then((v)=>{setLabs(v);setLabId(String(v[0]?.id||''))}).catch(e=>setError(String(e))) },[]);
 return <section className="panel" style={{maxWidth:560,margin:'40px auto',padding:24}}>
   <h1>Choose your lab</h1><p>Administrators must associate their account with a laboratory before continuing.</p>
   <label className="field">Lab <select className="input" value={labId} onChange={e=>setLabId(e.target.value)}>{labs.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
   {error&&<p role="alert" className="error">{error}</p>}
   <button className="button" disabled={!labId} onClick={async()=>{try{const u=await api('/auth/me/lab/',{method:'PATCH',body:JSON.stringify({lab_id:Number(labId)})});setActiveLabCode(u.lab_code);window.location.assign('/dashboard')}catch(e){setError(String(e))}}}>Continue</button>
 </section>;
}