import { redirect } from 'next/navigation';

export default function LegacyReadyToDisposePage() {
  redirect('/disposal/containers');
}
