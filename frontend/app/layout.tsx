import './globals.css';
import AppShell from '@/components/AppShell';
import ToastProvider from '@/components/ToastProvider';
import OutlookEmailManualCompose from '@/components/OutlookEmailManualCompose';

export const metadata = {
  title: 'Problem Samples Tracker',
  description: 'Problem sample management and tracking',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><ToastProvider><AppShell>{children}</AppShell><OutlookEmailManualCompose /></ToastProvider></body></html>;
}
