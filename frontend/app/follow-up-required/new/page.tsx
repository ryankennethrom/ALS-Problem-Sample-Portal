import { redirect } from 'next/navigation';

export default function LegacyNewTicketsPage() {
  redirect('/follow-up-required/tracking-not-sent');
}
