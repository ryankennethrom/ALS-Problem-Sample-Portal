'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { AdvancedFilter, MatchMode } from '@/components/AdvancedSearch';
import { ProblemTable } from '@/lib/problemTables';

type ProblemImage = {
  id: number;
  image: string;
  original_name?: string;
  size_bytes?: number;
  uploaded_at?: string;
};

type Problem = {
  id: string;
  problem_number: number;
  created_at: string;
  images?: ProblemImage[];
};

type QuickFilter = { field_key: string; value: string };

type GalleryImage = ProblemImage & {
  problemId: string;
  problemNumber: number;
  problemCreatedAt: string;
};

function parseArrayParam<T>(raw: string | null): T[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed as T[] : [];
  } catch {
    return [];
  }
}

function formatBytes(value?: number) {
  const bytes = Number(value || 0);
  if (!bytes) return 'Size unavailable';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function ImageSearchContent() {
  const searchParams = useSearchParams();
  const tableId = searchParams.get('table') || '';
  const q = searchParams.get('q') || '';
  const match: MatchMode = searchParams.get('match') === 'any' ? 'any' : 'all';
  const rawFilters = searchParams.get('filters');
  const rawQuickFilters = searchParams.get('quick_filters');
  const filters = useMemo(() => parseArrayParam<AdvancedFilter>(rawFilters), [rawFilters]);
  const quickFilters = useMemo(() => parseArrayParam<QuickFilter>(rawQuickFilters), [rawQuickFilters]);

  const [table, setTable] = useState<ProblemTable | null>(null);
  const [items, setItems] = useState<Problem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fullScreenImage, setFullScreenImage] = useState<GalleryImage | null>(null);

  useEffect(() => {
    if (!tableId) {
      setError('No ticket table was selected for this image search.');
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [tableData, problemData] = await Promise.all([
          api(`/problem-tables/${encodeURIComponent(tableId)}/`),
          (async () => {
            if (filters.length || quickFilters.length) {
              return api('/problem-samples/advanced-search/', {
                method: 'POST',
                body: JSON.stringify({
                  table: tableId,
                  q: q.trim(),
                  match,
                  filters,
                  quick_filters: quickFilters,
                }),
              });
            }
            const tableSuffix = `table=${encodeURIComponent(tableId)}`;
            return q.trim()
              ? api(`/problem-samples/search/?q=${encodeURIComponent(q.trim())}&${tableSuffix}`)
              : api(`/problem-samples/?${tableSuffix}`);
          })(),
        ]);
        if (cancelled) return;
        setTable(tableData as ProblemTable);
        setItems(Array.isArray(problemData) ? problemData : (problemData.results || []));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load image search results.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [tableId, q, match, filters, quickFilters]);

  useEffect(() => {
    if (!fullScreenImage) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullScreenImage(null);
    };
    window.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [fullScreenImage]);

  const images = useMemo<GalleryImage[]>(() => items.flatMap(problem =>
    (problem.images || []).filter(image => Boolean(image.image)).map(image => ({
      ...image,
      problemId: problem.id,
      problemNumber: problem.problem_number,
      problemCreatedAt: problem.created_at,
    })),
  ), [items]);

  const queryParts = [
    q.trim() ? `Search: “${q.trim()}”` : '',
    filters.length ? `${filters.length} advanced condition${filters.length === 1 ? '' : 's'} (${match === 'all' ? 'match all' : 'match any'})` : '',
    quickFilters.length ? `${quickFilters.length} quick filter${quickFilters.length === 1 ? '' : 's'}` : '',
  ].filter(Boolean);

  return <div>
    <div className="page-toolbar image-search-page-toolbar">
      <div>
        <div className="eyebrow">Ticket Table · Image Search</div>
        <h1 className="page-heading" style={{marginBottom:2}}>{table?.name || 'Image Search'}</h1>
        <div className="muted table-description">Images from the tickets matched by the table query you opened this gallery from.</div>
      </div>
      <div className="toolbar-actions">
        <Link className="button secondary" href={tableId ? `/problem-samples?table=${encodeURIComponent(tableId)}` : '/problem-samples'}>← Back to table</Link>
      </div>
    </div>

    <section className="panel panel-blue image-search-summary">
      <div className="image-search-summary-main">
        <div><strong>{loading ? 'Loading images…' : `${images.length} image${images.length === 1 ? '' : 's'}`}</strong>{!loading && <span className="muted"> from {items.length} matching ticket{items.length === 1 ? '' : 's'}</span>}</div>
        {queryParts.length > 0 && <div className="image-search-query-badges">{queryParts.map(part => <span className="badge blue" key={part}>{part}</span>)}</div>}
        {queryParts.length === 0 && <div className="muted result-meta">No filters are active. Showing images from the entire selected table.</div>}
      </div>
    </section>

    {error && <div className="card error" style={{marginTop:14}}>{error}</div>}

    {!loading && !error && images.length === 0 && <section className="panel image-search-empty" style={{marginTop:14}}>
      <div className="empty-schema-content">
        <div className="empty-schema-title">No images found</div>
        <div className="muted">The current table query matches no ticket images.</div>
      </div>
    </section>}

    {!error && images.length > 0 && <section className="image-search-gallery" aria-label="Ticket image search results">
      {images.map(image => <article className="image-search-card" key={`${image.problemId}-${image.id}`}>
        <button className="image-search-preview" type="button" onClick={() => setFullScreenImage(image)} title="View full screen">
          <img src={image.image} alt={image.original_name || `Ticket ${image.problemNumber} image`} />
        </button>
        <div className="image-search-card-body">
          <div className="image-search-card-heading">
            <div>
              <div className="image-search-ticket-label">Ticket #{image.problemNumber}</div>
              <div className="file-name">{image.original_name || 'Image'}</div>
            </div>
            <span className="muted image-search-date">{image.uploaded_at ? new Date(image.uploaded_at).toLocaleString() : ''}</span>
          </div>
          <div className="muted result-meta">{formatBytes(image.size_bytes)}</div>
          <div className="image-search-card-actions">
            <button className="button secondary" type="button" onClick={() => setFullScreenImage(image)}>Full screen</button>
            <Link className="button" href={`/problems/${image.problemId}`}>Go to ticket</Link>
          </div>
        </div>
      </article>)}
    </section>}

    {fullScreenImage && <div className="image-search-lightbox" role="dialog" aria-modal="true" aria-label={`Ticket ${fullScreenImage.problemNumber} image`} onMouseDown={event => {
      if (event.target === event.currentTarget) setFullScreenImage(null);
    }}>
      <div className="image-search-lightbox-shell">
        <div className="image-search-lightbox-header">
          <div>
            <strong>Ticket #{fullScreenImage.problemNumber}</strong>
            <span className="muted"> · {fullScreenImage.original_name || 'Image'}</span>
          </div>
          <div className="image-search-lightbox-actions">
            <Link className="button" href={`/problems/${fullScreenImage.problemId}`}>Go to ticket</Link>
            <button className="button secondary" type="button" onClick={() => setFullScreenImage(null)}>Close</button>
          </div>
        </div>
        <div className="image-search-lightbox-image-wrap">
          <img src={fullScreenImage.image} alt={fullScreenImage.original_name || `Ticket ${fullScreenImage.problemNumber} image`} />
        </div>
      </div>
    </div>}
  </div>;
}

export default function ImageSearchPage() {
  return <Suspense fallback={<div className="muted">Loading image search…</div>}><ImageSearchContent /></Suspense>;
}
