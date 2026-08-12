"use client";

import { useState } from "react";
import { SlidersHorizontal, Send } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export type SearchOptions = {
  limit: number;
  numCandidates: number;
};

const DEFAULT_OPTIONS: SearchOptions = { limit: 10, numCandidates: 100 };

export function ChatInput({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (query: string, options: SearchOptions) => void;
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SearchOptions>(DEFAULT_OPTIONS);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed, options);
    setQuery("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t bg-background p-4">
      <Popover>
        <PopoverTrigger
          className={buttonVariants({ variant: "outline", size: "icon" })}
          aria-label="Search options"
        >
          <SlidersHorizontal className="size-4" />
        </PopoverTrigger>
        <PopoverContent className="w-64" align="start">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="limit">Results to return</Label>
              <Input
                id="limit"
                type="number"
                min={1}
                max={100}
                value={options.limit}
                onChange={(event) =>
                  setOptions((current) => ({
                    ...current,
                    limit: Number(event.target.value) || DEFAULT_OPTIONS.limit,
                  }))
                }
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="numCandidates">Candidates considered</Label>
              <Input
                id="numCandidates"
                type="number"
                min={1}
                max={10000}
                value={options.numCandidates}
                onChange={(event) =>
                  setOptions((current) => ({
                    ...current,
                    numCandidates: Number(event.target.value) || DEFAULT_OPTIONS.numCandidates,
                  }))
                }
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Higher candidate counts can improve accuracy at the cost of speed.
            </p>
          </div>
        </PopoverContent>
      </Popover>
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="e.g. senior python backend engineer with AWS experience"
        disabled={disabled}
        autoFocus
      />
      <Button type="submit" disabled={disabled || !query.trim()}>
        <Send className="size-4" />
        <span className="hidden sm:inline">Search</span>
      </Button>
    </form>
  );
}
