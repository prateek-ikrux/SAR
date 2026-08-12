import { Skeleton } from "@/components/ui/skeleton";
import { ProfileCard } from "@/components/search/profile-card";
import type { SearchResult } from "@/lib/api";

export type Turn = {
  id: string;
  query: string;
  status: "loading" | "done" | "error";
  results: SearchResult[];
  errorMessage?: string;
};

export function ChatTurn({ turn }: { turn: Turn }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="self-end rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
        {turn.query}
      </div>

      {turn.status === "loading" && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {turn.status === "error" && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {turn.errorMessage ?? "Something went wrong running that search."}
        </div>
      )}

      {turn.status === "done" && turn.results.length === 0 && (
        <p className="px-1 text-sm text-muted-foreground">No matching profiles found.</p>
      )}

      {turn.status === "done" && turn.results.length > 0 && (
        <div className="flex flex-col gap-3">
          {turn.results.map((result) => (
            <ProfileCard key={result._id} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}
