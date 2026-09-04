import './globals.css';
import AppShell from '@/components/AppShell';
import ToastProvider from '@/components/ToastProvider';

export const metadata = {
  title: 'Edmonton Problem Sample Tracker',
  description: 'Internal problem sample tracker',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><ToastProvider><AppShell>{children}</AppShell></ToastProvider></body></html>;
}
