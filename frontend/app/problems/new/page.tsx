import ProblemForm from '@/components/ProblemForm';

export default function NewProblem() {
  return <div>
    <h1 className="page-heading">New Problem Sample</h1>
    <section className="panel panel-blue">
      <div className="panel-header">Problem Sample Details</div>
      <div className="panel-body"><ProblemForm/></div>
    </section>
  </div>;
}
