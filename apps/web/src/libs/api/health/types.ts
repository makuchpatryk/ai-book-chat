import type { ComponentStatus } from "@libs/types/shared";

export interface HealthResponse {
  status: ComponentStatus;
  database: ComponentStatus;
  redis: ComponentStatus;
}
