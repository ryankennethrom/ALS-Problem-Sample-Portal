import './globals.css';
import AppShell from '@/components/AppShell';
import ToastProvider from '@/components/ToastProvider';

export const metadata = {
  title: 'Edmonton Ticket Tracker',
  description: 'Internal ticket tracker',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><ToastProvider><AppShell>{children}</AppShell></ToastProvider></body></html>;
}
