import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ChevronLeft, ChevronRight, Loader2, Search, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import ResultCard from "@/components/ResultCard";
import ProfileSheet from "@/components/ProfileSheet";
import { errorMessage } from "@/lib/api";
import { usePrefetchProfile, useResumeLink, useSearch } from "@/hooks/useSearch";
import { useUiStore } from "@/stores/uiStore";

const PAGE_SIZES = ["10", "20", "50"];

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const inputRef = useRef(null);

  const query = params.get("q") || "";
  const page = Number(params.get("page") || 1);
  const pageSize = Number(params.get("size") || 10);
  const collapse = params.get("collapse") !== "0";

  const [draft, setDraft] = useState(query);
  const [profileId, setProfileId] = useState(null);

  const { recentSearches, addRecentSearch, clearRecentSearches, showScores, toggleScores } =
    useUiStore();
  const prefetchProfile = usePrefetchProfile();
  const resumeLink = useResumeLink();

  const { data, isFetching, error, refetch } = useSearch({ query, page, pageSize, collapse });

  useEffect(() => setDraft(query), [query]);

  // "/" focuses the search box, the way every search-first tool behaves.
  useEffect(() => {
    function onKeyDown(event) {
      const typingElsewhere = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
      if (event.key === "/" && !typingElsewhere) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function runSearch(nextQuery, overrides = {}) {
    const q = (nextQuery ?? draft).trim();
    if (!q) return;
    addRecentSearch(q);
    const next = {
      q,
      page: String(overrides.page ?? 1),
      size: String(overrides.size ?? pageSize),
      ...(collapse ? {} : { collapse: "0" }),
      ...(overrides.collapse === false ? { collapse: "0" } : {}),
    };
    if (overrides.collapse === true) delete next.collapse;

    // Searching the same text again must actually search again. Identical
    // params leave the URL untouched, so nothing would re-run on its own.
    const unchanged = new URLSearchParams(next).toString() === params.toString();
    setParams(next);
    if (unchanged) refetch();
  }

  function openResume(id) {
    resumeLink.mutate(id, {
      onSuccess: (link) => {
        const opened = window.open(link.url, "_blank", "noopener,noreferrer");
        if (!opened) toast.error("Your browser blocked the pop-up.");
      },
      onError: (err) => {
        const message = errorMessage(err, "Could not open the resume.");
        toast.error(
          err?.response?.status === 404
            ? "No PDF for this candidate. Around one profile in five is missing from storage."
            : message,
        );
      },
    });
  }

  const results = data?.results ?? [];
  const showEmpty = query && !isFetching && results.length === 0;

  return (
    <div className="space-y-5">
      {/* ---------------------------------------------------------- search bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <div className="relative min-w-64 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Describe the candidate, or paste an email or phone number…"
            className="pl-9"
            aria-label="Search candidates"
          />
          {draft && (
            <button
              type="button"
              onClick={() => {
                setDraft("");
                inputRef.current?.focus();
              }}
              className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        <Select
          value={String(pageSize)}
          onValueChange={(value) => runSearch(query || draft, { size: Number(value) })}
        >
          <SelectTrigger className="w-24" aria-label="Results per page">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((size) => (
              <SelectItem key={size} value={size}>
                {size} / page
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button type="submit" disabled={isFetching || !draft.trim()}>
          {isFetching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          Search
        </Button>
      </form>

      {/* ---------------------------------------------------------- recents */}
      {!query && recentSearches.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Recent</span>
          {recentSearches.map((recent) => (
            <Badge
              key={recent}
              variant="secondary"
              className="cursor-pointer font-normal"
              onClick={() => {
                setDraft(recent);
                runSearch(recent);
              }}
            >
              {recent}
            </Badge>
          ))}
          <Button variant="ghost" size="sm" onClick={clearRecentSearches}>
            Clear
          </Button>
        </div>
      )}

      {/* ---------------------------------------------------------- meta */}
      {data && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span>
            {data.strategy === "identifier"
              ? "Exact identifier lookup"
              : `Vector search · ${data.mode?.toUpperCase()}`}
          </span>
          <span>·</span>
          <span>
            showing {results.length} of {data.total_in_pool} matched
          </span>
          <span>·</span>
          <span>{data.took_ms} ms</span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={toggleScores}>
            {showScores ? "Hide scores" : "Show scores"}
          </Button>
        </div>
      )}

      {/* ---------------------------------------------------------- results */}
      {error && (
        <Card className="p-4 text-sm text-destructive">
          {errorMessage(error, "Search failed.")}
        </Card>
      )}

      {isFetching && results.length === 0 && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="gap-2 p-4">
              <Skeleton className="h-5 w-56" />
              <Skeleton className="h-4 w-72" />
              <Skeleton className="h-4 w-full" />
            </Card>
          ))}
        </div>
      )}

      {showEmpty && (
        <Card className="p-8 text-center">
          <p className="font-medium">No matches</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Try describing the role in plain language — seniority, stack, domain — rather than
            keywords alone.
          </p>
        </Card>
      )}

      {!query && recentSearches.length === 0 && (
        <Card className="p-8 text-center">
          <p className="font-medium">Search 122,000 resumes</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Describe who you are looking for, or paste an email address or phone number to jump
            straight to one person. Press <kbd className="font-mono">/</kbd> to focus the box.
          </p>
        </Card>
      )}

      <div className={isFetching && results.length > 0 ? "space-y-2 opacity-60" : "space-y-2"}>
        {results.map((hit) => (
          <ResultCard
            key={hit.id}
            hit={hit}
            onOpen={setProfileId}
            onResume={openResume}
            onPrefetch={prefetchProfile}
            resumePending={resumeLink.isPending}
          />
        ))}
      </div>

      {/* ---------------------------------------------------------- pagination */}
      {results.length > 0 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || isFetching}
            onClick={() => runSearch(query, { page: page - 1 })}
          >
            <ChevronLeft className="size-4" />
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">Page {page}</span>
          <Button
            variant="outline"
            size="sm"
            disabled={!data?.has_more || isFetching}
            onClick={() => runSearch(query, { page: page + 1 })}
          >
            Next
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}

      <ProfileSheet
        profileId={profileId}
        onOpenChange={setProfileId}
        onResume={openResume}
        resumePending={resumeLink.isPending}
      />
    </div>
  );
}
