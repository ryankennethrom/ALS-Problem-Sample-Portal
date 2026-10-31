import { NextRequest, NextResponse } from 'next/server';

// Existing emailed /reports/monthly/<token> links remain valid, but now
// download the Excel workbook rather than displaying an HTML report.
export function GET(request: NextRequest, context: { params: Promise<{ token: string }> }) {
  return context.params.then(({ token }) => {
    if (!/^[0-9a-f-]{36}$/i.test(token)) return new NextResponse('Report not found.', {status:404});
    const url = new URL(`/backend-api/public/monthly-reports/${encodeURIComponent(token)}/xlsx/`, request.url);
    const response = NextResponse.redirect(url, 307);
    response.headers.set('Cache-Control', 'private, no-store, max-age=0');
    response.headers.set('Referrer-Policy', 'no-referrer');
    return response;
  });
}
