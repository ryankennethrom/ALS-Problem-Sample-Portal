/** Staff-only physical-handling reminder for terminal sample workflows. */
export const RACK_REMOVAL_WORKFLOWS = ['Shipped back to client', 'Back to testing'] as const;

export function needsRackRemovalReminder(workflow: unknown): boolean {
  return RACK_REMOVAL_WORKFLOWS.includes(workflow as (typeof RACK_REMOVAL_WORKFLOWS)[number]);
}

export function rackRemovalReminder(ticketCount = 1): string {
  const plural = ticketCount !== 1;
  return `Remove ${plural ? 'the selected tickets' : 'the ticket'} from the problem sample rack to prevent accidental disposal.`;
}
