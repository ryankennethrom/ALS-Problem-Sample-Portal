import { Suspense } from 'react';
import ProblemForm from '@/components/ProblemForm';

export default function NewProblem() {
  return <div>
    <h1 className="page-heading">New Ticket</h1>
    <section className="panel panel-blue">
      <div className="panel-header">Ticket Details</div>
      <div className="panel-body"><Suspense fallback={<div className="muted">Loading form…</div>}><ProblemForm/></Suspense></div>
    </section>
  </div>;
}
