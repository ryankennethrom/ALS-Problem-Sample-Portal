/** Customer tracking links are viewable to staff, but only admins get link actions. */
export default function TrackingLinkDisplay({
  url,
  canOpen,
  fullUrl = false,
}: {
  url?: string | null;
  canOpen: boolean;
  fullUrl?: boolean;
}) {
  if (!url) return <>—</>;
  if (canOpen) {
    return <a className={fullUrl ? 'table-link tracking-link-value' : 'table-link'} href={url} target="_blank" rel="noreferrer">
      {fullUrl ? url : 'Open tracking link'}
    </a>;
  }
  return <span className="tracking-link-noninteractive tracking-link-value" draggable={false}
    onCopy={event => event.preventDefault()} onCut={event => event.preventDefault()}
    onDragStart={event => event.preventDefault()}
    title="Tracking link is view-only for non-admin staff">{url}</span>;
}
