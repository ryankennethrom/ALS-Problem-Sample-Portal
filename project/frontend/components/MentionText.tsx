import React from 'react';

const MENTION_SPLIT = /(@[A-Za-z0-9_](?:[A-Za-z0-9_.+-]*[A-Za-z0-9_])?)/g;
const MENTION_EXACT = /^@[A-Za-z0-9_](?:[A-Za-z0-9_.+-]*[A-Za-z0-9_])?$/;

export default function MentionText({ text }: { text: string }) {
  return <>{String(text || '').split(MENTION_SPLIT).map((part, index) =>
    MENTION_EXACT.test(part)
      ? <span className="mention-token" key={`${part}-${index}`}>{part}</span>
      : <React.Fragment key={`text-${index}`}>{part}</React.Fragment>
  )}</>;
}
