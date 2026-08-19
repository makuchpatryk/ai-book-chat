import type { ComponentStatus } from "@/types/shared";

export interface HealthResponse {
  status: ComponentStatus;
  database: ComponentStatus;
  redis: ComponentStatus;
}
