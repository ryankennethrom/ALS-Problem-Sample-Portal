'use client';

import { ImgHTMLAttributes, useEffect, useState } from 'react';
import { apiBlob } from '@/lib/api';

type StaffImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  problemId: string | number;
  imageId: number;
  openInNewTab?: boolean;
};

export function staffImageContentPath(problemId: string | number, imageId: number) {
  return `/problem-samples/${encodeURIComponent(String(problemId))}/images/${imageId}/content/`;
}

export default function StaffImage({ problemId, imageId, openInNewTab = false, className = '', alt, ...imgProps }: StaffImageProps) {
  const [src, setSrc] = useState('');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl = '';
    setSrc('');
    setFailed(false);

    apiBlob(staffImageContentPath(problemId, imageId))
      .then(blob => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [problemId, imageId]);

  if (failed) {
    return <div className={`staff-image-state ${className}`} role="img" aria-label={`${alt || 'Ticket image'} unavailable`}>
      <span>Image file unavailable</span>
    </div>;
  }

  if (!src) {
    return <div className={`staff-image-state ${className}`} role="status" aria-label="Loading ticket image">
      <span>Loading image…</span>
    </div>;
  }

  const image = <img {...imgProps} className={className} src={src} alt={alt || 'Ticket image'} />;
  if (!openInNewTab) return image;

  return <button
    type="button"
    className="staff-image-open"
    title="Open image in a new tab"
    onClick={() => window.open(src, '_blank', 'noopener,noreferrer')}
  >{image}</button>;
}
