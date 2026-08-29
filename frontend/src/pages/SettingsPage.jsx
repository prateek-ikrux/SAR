import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useSettings, useUpdateSettings } from "@/hooks/useSettings";
import { cn } from "@/lib/utils";

const MODES = [
  {
    value: true,
    name: "ENN",
    subtitle: "Exhaustive nearest neighbour",
    detail:
      "Scores every resume in the index. Deterministic — the same query always returns the same ranking.",
    cost: "~800 ms – 1.1 s per new query",
  },
  {
    value: false,
    name: "ANN",
    subtitle: "Approximate nearest neighbour",
    detail:
      "Searches a candidate subset. Roughly twice as fast, and in practice the top results have matched ENN closely.",
    cost: "~450 – 700 ms per new query",
  },
];

function ModeCard({ mode, selected, disabled, onSelect }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect(mode.value)}
      aria-pressed={selected}
      className={cn(
        "flex w-full flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        selected ? "border-foreground/40 bg-secondary" : "hover:border-foreground/25",
        disabled && "pointer-events-none opacity-60",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <span className="font-medium">{mode.name}</span>
        <span className="text-sm text-muted-foreground">{mode.subtitle}</span>
        {selected && <Check className="ml-auto size-4" />}
      </div>
      <p className="text-sm text-muted-foreground">{mode.detail}</p>
      <Badge variant="outline" className="mt-1 font-normal">
        {mode.cost}
      </Badge>
    </button>
  );
}

export default function SettingsPage() {
  const { data: settings, isPending, error } = useSettings();
  const update = useUpdateSettings();

  function select(value) {
    if (settings?.search_exact === value) return;
    update.mutate(
      { search_exact: value },
      {
        onSuccess: (data) =>
          toast.success(`Search mode set to ${data.search_exact ? "ENN" : "ANN"} for everyone.`),
        onError: (err) => toast.error(errorMessage(err, "Could not save the setting.")),
      },
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Search mode</CardTitle>
          <CardDescription>
            Applies to everyone. Recruiters cannot change it — each search response simply reports
            which mode ran.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {isPending && (
            <>
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </>
          )}

          {error && (
            <p className="text-sm text-destructive">
              {errorMessage(error, "Could not load settings.")}
            </p>
          )}

          {settings &&
            MODES.map((mode) => (
              <ModeCard
                key={mode.name}
                mode={mode}
                selected={settings.search_exact === mode.value}
                disabled={update.isPending}
                onSelect={select}
              />
            ))}

          {update.isPending && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              Saving…
            </p>
          )}

          {settings?.updated_at && (
            <p className="text-xs text-muted-foreground">
              Last changed {new Date(settings.updated_at).toLocaleString()}
              {settings.updated_by ? ` by ${settings.updated_by}` : ""}.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
