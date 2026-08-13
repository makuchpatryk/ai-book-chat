/**
 * App-local API types. Deliberately NOT shared with the backend package —
 * each app owns its own types (see specs/basic-structure.md).
 */

export type ComponentStatus = "ok" | "error";

export interface HealthResponse {
  status: ComponentStatus;
  database: ComponentStatus;
  redis: ComponentStatus;
}
