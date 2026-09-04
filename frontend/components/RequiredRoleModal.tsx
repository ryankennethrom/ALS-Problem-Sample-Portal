'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

type Role = 'lab_technician' | 'customer_service';
export type RoleModalUser = {
  id: number;
  email: string;
  name: string;
  role: string;
  role_label: string;
  needs_role: boolean;
};

export default function RequiredRoleModal({
  user,
  onSaved,
}: {
  user: RoleModalUser;
  onSaved: (user: RoleModalUser) => void;
}) {
  const [role, setRole] = useState<Role | ''>('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function saveRole() {
    if (!role || saving) return;
    setSaving(true);
    setError('');
    try {
      const updated: RoleModalUser = await api('/auth/me/', {
        method: 'PATCH',
        body: JSON.stringify({ role }),
        successMessage: 'Role selected successfully.',
        errorMessage: 'Could not save your role',
      });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your role.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="required-role-overlay" role="presentation">
      <section
        className="required-role-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="required-role-title"
        aria-describedby="required-role-description"
      >
        <div className="required-role-badge">Account setup required</div>
        <h2 id="required-role-title">Choose your role to continue</h2>
        <p id="required-role-description" className="required-role-copy">
          Your new account needs a role before you can use the Edmonton Problem Sample Tracker.
          Choose the option that best matches your work.
        </p>

        <div className="required-role-options" role="radiogroup" aria-label="Choose your role">
          <button
            type="button"
            className={`required-role-option ${role === 'lab_technician' ? 'selected' : ''}`}
            role="radio"
            aria-checked={role === 'lab_technician'}
            onClick={() => setRole('lab_technician')}
            disabled={saving}
          >
            <span className="required-role-radio" aria-hidden="true" />
            <span>
              <strong>Lab Technician</strong>
              <small>For laboratory staff handling and updating problem samples.</small>
            </span>
          </button>

          <button
            type="button"
            className={`required-role-option ${role === 'customer_service' ? 'selected' : ''}`}
            role="radio"
            aria-checked={role === 'customer_service'}
            onClick={() => setRole('customer_service')}
            disabled={saving}
          >
            <span className="required-role-radio" aria-hidden="true" />
            <span>
              <strong>Customer Service</strong>
              <small>For customer-service staff following up with clients.</small>
            </span>
          </button>
        </div>

        {error && <div className="required-role-error" role="alert">{error}</div>}

        <button
          type="button"
          className="button required-role-continue"
          onClick={saveRole}
          disabled={!role || saving}
        >
          {saving ? 'Saving…' : 'Continue'}
        </button>
        <p className="required-role-note">You can change your role later from My Account.</p>
      </section>
    </div>
  );
}
