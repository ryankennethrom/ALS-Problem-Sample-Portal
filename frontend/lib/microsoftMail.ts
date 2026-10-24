import { api } from '@/lib/api';

export type MicrosoftMailStatus = { configured: boolean; connected: boolean; email: string; redirect_uri: string; mode: string };
export type MicrosoftEmail = { to: string[]; cc: string[]; subject: string; body: string };

export async function microsoftMailStatus(): Promise<MicrosoftMailStatus> {
  return api('/auth/microsoft/status/');
}
export async function sendWithMicrosoft365(message: MicrosoftEmail, idempotencyKey: string): Promise<{status: string; message: string}> {
  return api('/auth/microsoft/send/', {
    method: 'POST',
    body: JSON.stringify({ ...message, idempotency_key: idempotencyKey }),
  });
}
