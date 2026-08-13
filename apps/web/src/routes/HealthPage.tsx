import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/health";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ComponentStatus } from "@/types";

function StatusBadge({ label, status }: { label: string; status: ComponentStatus }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <Badge variant={status === "ok" ? "default" : "destructive"}>{status}</Badge>
    </div>
  );
}

export function HealthPage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 10_000,
  });

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>Backend status</CardTitle>
        <CardDescription>Live from GET /api/health, polled every 10s.</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending && <p className="text-sm text-muted-foreground">Checking…</p>}
        {isError && (
          <p className="text-sm text-destructive">API unreachable: {(error as Error).message}</p>
        )}
        {data && (
          <div>
            <StatusBadge label="Overall" status={data.status} />
            <StatusBadge label="Database" status={data.database} />
            <StatusBadge label="Redis" status={data.redis} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
