import { redirect } from 'next/navigation';

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ table?: string | string[] }>;
}) {
  const { table } = await searchParams;
  const tableId = Array.isArray(table) ? table[0] : table;
  redirect(tableId ? `/problem-samples?table=${encodeURIComponent(tableId)}` : '/dashboard');
}
