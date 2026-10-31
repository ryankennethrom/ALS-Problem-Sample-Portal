/** Display tracking URLs in text without providing a clickable or copyable link UI to staff. */
import React from 'react';

const TRACKING_URL = /((?:https?:\/\/[^\s"<>]+)?\/track\/[A-Za-z0-9_-]+(?:\?[^\s"<>]*)?)/gi;

export function TrackingLinkInlineText({ text }: { text: string }) {
  return <>{String(text || '').split(TRACKING_URL).map((segment, index) =>
    /^((?:https?:\/\/[^\s"<>]+)?\/track\/[A-Za-z0-9_-]+)/i.test(segment)
      ? <span className="tracking-link-noninteractive" draggable={false}
          onCopy={event => event.preventDefault()} onCut={event => event.preventDefault()}
          onDragStart={event => event.preventDefault()} key={index}>{segment}</span>
      : <React.Fragment key={index}>{segment}</React.Fragment>
  )}</>;
}

export default function TrackingLinkPreviewText({ text }: { text: string }) {
  return <div className="textarea customer-email-body tracking-link-preview-text">
    <TrackingLinkInlineText text={text} />
  </div>;
}
