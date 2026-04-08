import { NextRequest, NextResponse } from 'next/server';

// Server-side: prefer ORCHESTRATOR_INTERNAL_URL (Docker DNS), fall back to public URL
const ORCH = process.env.ORCHESTRATOR_INTERNAL_URL
  || process.env.NEXT_PUBLIC_ORCHESTRATOR_URL
  || 'http://localhost:8000';

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${ORCH}/${path.join('/')}${req.nextUrl.search}`;
  try {
    const res = await fetch(url, { cache: 'no-store' });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: 'Failed to reach orchestrator', detail: message }, { status: 502 });
  }
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${ORCH}/${path.join('/')}`;
  const contentType = req.headers.get('content-type') || '';

  try {
    let res: Response;
    if (contentType.includes('multipart/form-data')) {
      const formData = await req.formData();
      res = await fetch(url, { method: 'POST', body: formData });
    } else {
      const body = await req.text();
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
    }
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: 'Failed to reach orchestrator', detail: message }, { status: 502 });
  }
}
