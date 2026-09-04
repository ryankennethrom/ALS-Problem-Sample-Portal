'use client';

export default function LegacyVerifyPage() {
  return <div className="login-screen">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-brand-area">
        <img className="login-logo" src="/als-logo.png" alt="ALS" />
        <h1 id="login-title">Edmonton Problem<br />Sample Tracker</h1>
      </div>
      <div className="login-divider" />
      <div className="login-form-area">
        <p className="login-prompt">Email sign-in is disabled</p>
        <p className="login-subprompt">Use the username and password provided by a tracker administrator.</p>
        <button className="login-primary-button" type="button" onClick={() => window.location.replace('/login')}>
          Go to Sign In
        </button>
      </div>
    </section>
  </div>;
}
