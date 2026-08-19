/**
 * Feature-local types (UI state, filters, local only).
 *
 * For API types, import from @/api/chat/types instead.
 */

export interface ChatStreamState {
  status: "idle" | "streaming" | "error";
  liveText: string;
  error: string | null;
  pendingUserText: string | null;
}
