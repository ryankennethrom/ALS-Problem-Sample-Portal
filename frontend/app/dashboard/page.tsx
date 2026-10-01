'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useCurrentUser } from '@/components/CurrentUserContext';
import styles from './dashboard.module.css';

type Range = 'week' | 'month' | 'six_months' | 'year' | 'custom';
type Point = { period: string; label: string; count: number };
type Data = {
  generated_at: string;
  counts: { tracking_emails_today:number; customer_responded:number; tracking_not_sent:number; old_tickets:number; to_be_shipped:number; to_be_back_to_testing:number; day:number; week:number; month:number; six_months:number; year:number; custom:number|null };
  old_ticket_definition: { age_months:number; created_before:string };
  chart: { range:Range; range_label:string; bucket:string; total:number; points:Point[] };
  automatic_disposal_chart: { range:Range; range_label:string; bucket:string; total:number; points:Point[] };
};

const options: [Range,string][] = [
  ['week','Week'], ['month','Month'], ['six_months','6 Months'], ['year','Year'], ['custom','Custom']
];
const format = (v:number|null|undefined) => v == null ? '—' : new Intl.NumberFormat('en-CA').format(v);
function dateOffset(days:number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,10);
}

function Chart({points,ariaLabel,tooltipNoun='ticket'}:{points:Point[];ariaLabel:string;tooltipNoun?:string}) {
  const W=920,H=320,L=52,R=20,T=20,B=56,iw=W-L-R,ih=H-T-B;
  const max=Math.max(1,...points.map(p=>p.count));
  const ymax=max<=4?4:Math.ceil(max/4)*4;
  const step=points.length<2?0:iw/(points.length-1);
  const pts=points.map((p,i)=>({...p,x:L+(points.length<2?iw/2:i*step),y:T+ih-p.count/ymax*ih}));
  const line=pts.map(p=>`${p.x},${p.y}`).join(' ');
  const every=Math.max(1,Math.ceil(points.length/8));
  return <div className={styles.scroll}>
    <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} role="img" aria-label={ariaLabel}>
      {[0,1,2,3,4].map(i=>{const v=Math.round(ymax*i/4),y=T+ih-v/ymax*ih;return <g key={i}>
        <line x1={L} x2={W-R} y1={y} y2={y} className={styles.grid}/>
        <text x={L-8} y={y+4} textAnchor="end">{v}</text>
      </g>})}
      {pts.length>1 && <polyline points={line} className={styles.line} fill="none"/>}
      {pts.map((p,i)=><g key={p.period}>
        <circle cx={p.x} cy={p.y} r="4" className={styles.point}>
          <title>{p.label}: {p.count} {tooltipNoun}{p.count===1?'':'s'}</title>
        </circle>
        {(i%every===0||i===pts.length-1) && <text x={p.x} y={H-21} textAnchor="middle">{p.label.replace('Week of ','')}</text>}
      </g>)}
    </svg>
  </div>;
}

export default function Dashboard() {
  const currentUser = useCurrentUser();
  const [range,setRange]=useState<Range>('week');
  const [start,setStart]=useState(()=>dateOffset(-30));
  const [end,setEnd]=useState(()=>dateOffset(0));
  const [appliedStart,setAppliedStart]=useState('');
  const [appliedEnd,setAppliedEnd]=useState('');
  const [data,setData]=useState<Data|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');

  useEffect(()=>{
    let stop=false;
    if(range==='custom'&&(!appliedStart||!appliedEnd)){setLoading(false);return;}
    setLoading(true); setError('');
    const q=new URLSearchParams({range});
    if(appliedStart&&appliedEnd){q.set('start_date',appliedStart);q.set('end_date',appliedEnd);}
    api(`/dashboard/?${q.toString()}`)
      .then((d:Data)=>{if(!stop)setData(d);})
      .catch(e=>{if(!stop)setError(e instanceof Error?e.message:'Could not load dashboard');})
      .finally(()=>{if(!stop)setLoading(false);});
    return()=>{stop=true;};
  },[range,appliedStart,appliedEnd]);

  function applyCustom(){
    if(!start||!end){setError('Choose both custom dates.');return;}
    if(end<start){setError('Custom end date cannot be before the start date.');return;}
    setError(''); setAppliedStart(start); setAppliedEnd(end); setRange('custom');
  }

  const cards = [
    ['Last day',data?.counts.day,'Past 24 hours'],
    ['Last week',data?.counts.week,'Past 7 days'],
    ['Last month',data?.counts.month,'Past 30 days'],
    ['Last 6 months',data?.counts.six_months,'Past 183 days'],
    ['Last year',data?.counts.year,'Past 365 days'],
    ['Custom',data?.counts.custom,appliedStart&&appliedEnd?`${appliedStart} → ${appliedEnd}`:'Choose dates below'],
  ] as const;

  return <div>
    <div className="page-heading-row"><div>
      <h1 className="page-heading">Dashboard</h1>
    </div></div>

    <section className={styles.dashboardSection} aria-labelledby="action-required-heading">
      <h2 id="action-required-heading" className={styles.sectionHeading}>Action Required</h2>

      <section className={styles.newCard} aria-label="Tracking Not Sent">
        <div>
          <div className={styles.label}>Tracking Not Sent</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.tracking_not_sent)}</div>
          <div className={styles.note}>Open workflows · no tracking link · all tables</div>
        </div>
        <Link href="/follow-up-required/tracking-not-sent" className={styles.seeAll}>See all &gt;</Link>
      </section>

      <section className={styles.newCard} aria-label="New Customer Response">
        <div>
          <div className={styles.label}>New Customer Response</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.customer_responded)}</div>
          <div className={styles.note}>Across all tables · current workflow</div>
        </div>
        <Link href="/follow-up-required/customer-responded" className={styles.seeAll}>See all &gt;</Link>
      </section>

      <section className={styles.newCard} aria-label="To be shipped">
        <div>
          <div className={styles.label}>To be shipped</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.to_be_shipped)}</div>
          <div className={styles.note}>Awaiting shipment · all tables</div>
        </div>
        <Link href="/shipping/to-be-shipped" className={styles.seeAll}>See all &gt;</Link>
      </section>

      <section className={styles.newCard} aria-label="To be back to testing">
        <div>
          <div className={styles.label}>To be back to testing</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.to_be_back_to_testing)}</div>
          <div className={styles.note}>Awaiting return to testing · all tables</div>
        </div>
        <Link href="/to-be-back-to-testing" className={styles.seeAll}>See all &gt;</Link>
      </section>

      <section className={styles.newCard} aria-label="Old Tickets">
        <div>
          <div className={styles.label}>Old Tickets</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.old_tickets)}</div>
          <div className={styles.note}>Created before {data?.old_ticket_definition.created_before || 'the configured age'} · all tables and workflows</div>
        </div>
        {currentUser?.is_admin && <Link href="/terminal-ticket-cleanup" className={styles.seeAll}>Delete old tickets &gt;</Link>}
      </section>
    </section>

    <section className={styles.dashboardSection} aria-labelledby="analytics-heading">
      <h2 id="analytics-heading" className={styles.sectionHeading}>Analytics</h2>

      <section className={styles.newCard} aria-label="Tracking emails sent today">
        <div>
          <div className={styles.label}>Tracking Emails Sent Today</div>
          <div className={styles.value}>{loading&&!data?'…':format(data?.counts.tracking_emails_today)}</div>
          <div className={styles.note}>Tracking links created today · local time</div>
        </div>
      </section>

    <p className={`muted ${styles.sectionIntro}`}>Tickets opened in the last…</p>
    <div className={styles.cards}>{cards.map(([label,value,note])=><div className={styles.card} key={label}>
      <div className={styles.label}>{label}</div>
      <div className={styles.value}>{loading&&!data?'…':format(value)}</div>
      <div className={styles.note}>{note}</div>
    </div>)}</div>

    <section className="panel">
      <div className="panel-header">Custom date range</div>
      <div className={`panel-body ${styles.custom}`}>
        <label>Start date<input className="input" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
        <label>End date<input className="input" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
        <button className="button" type="button" onClick={applyCustom}>Apply custom range</button>
      </div>
    </section>

    {error && <div className={styles.error}>{error}</div>}

    <section className={`panel ${styles.chartPanel}`}>
      <div className={`panel-header ${styles.header}`}>
        <div><div>Tickets opened over time</div><small>{data?.chart.range_label||'Select a range'}</small></div>
        <div className={styles.tabs}>{options.map(([key,label])=><button type="button" key={key} className={range===key?styles.active:''} disabled={key==='custom'&&(!appliedStart||!appliedEnd)} onClick={()=>setRange(key)}>{label}</button>)}</div>
      </div>
      <div className="panel-body">
        {loading?<div className={styles.loading}>Loading dashboard…</div>:data?.chart?<>
          <div className={styles.summary}><strong>{format(data.chart.total)}</strong> opened · grouped by {data.chart.bucket}</div>
          <Chart points={data.chart.points} ariaLabel="Tickets opened over time"/>
        </>:<div className={styles.loading}>Apply a custom range to view the graph.</div>}
      </div>
    </section>

    <section className={`panel ${styles.chartPanel}`}>
      <div className={`panel-header ${styles.header}`}>
        <div>
          <div>Automatic disposal expiries</div>
          <small>{data?.automatic_disposal_chart.range_label||'Select a range'}</small>
        </div>
        <div className={styles.tabs}>{options.map(([key,label])=><button type="button" key={key} className={range===key?styles.active:''} disabled={key==='custom'&&(!appliedStart||!appliedEnd)} onClick={()=>setRange(key)}>{label}</button>)}</div>
      </div>
      <div className="panel-body">
        {loading?<div className={styles.loading}>Loading dashboard…</div>:data?.automatic_disposal_chart?<>
          <div className={styles.summary}><strong>{format(data.automatic_disposal_chart.total)}</strong> moved to To be Disposed by automatic expiry · grouped by {data.automatic_disposal_chart.bucket}</div>
          <Chart points={data.automatic_disposal_chart.points} ariaLabel="Tickets moved to To be Disposed by automatic disposal expiry over time" tooltipNoun="ticket"/>
        </>:<div className={styles.loading}>Apply a custom range to view the graph.</div>}
      </div>
    </section>
    </section>
  </div>;
}
