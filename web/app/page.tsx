"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { RequireAuth } from "@/components/auth/require-auth";
import { Header } from "@/components/layout/header";
import { ChatInput, type SearchOptions } from "@/components/search/chat-input";
import { ChatTurn, type Turn } from "@/components/search/chat-turn";
import { useAuth } from "@/lib/auth-context";
import { ApiError, search } from "@/lib/api";

const SESSION_KEY = "sar.turns";
const EXAMPLE_QUERIES = [
  "senior python backend engineer with AWS experience",
  "product designer with fintech background",
  "data scientist skilled in NLP and PyTorch",
];

function loadTurns(): Turn[] {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Turn[]) : [];
  } catch {
    return [];
  }
}

export default function SearchPage() {
  return (
    <RequireAuth>
      <SearchScreen />
    </RequireAuth>
  );
}

function SearchScreen() {
  const { auth, logout } = useAuth();
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTurns(loadTurns());
  }, []);

  useEffect(() => {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(turns));
  }, [turns]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function runSearch(query: string, options: SearchOptions) {
    if (!auth) return;

    const turnId = crypto.randomUUID();
    setTurns((current) => [
      ...current,
      { id: turnId, query, status: "loading", results: [] },
    ]);
    setIsSearching(true);

    try {
      const response = await search(auth.token, query, options.limit, options.numCandidates);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === turnId ? { ...turn, status: "done", results: response.results } : turn,
        ),
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout();
        router.replace("/login");
        return;
      }
      setTurns((current) =>
        current.map((turn) =>
          turn.id === turnId
            ? {
                ...turn,
                status: "error",
                errorMessage: error instanceof ApiError ? error.message : "Search failed.",
              }
            : turn,
        ),
      );
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Header />
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-6">
        {turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <div className="rounded-full bg-muted p-4">
              <Search className="size-6 text-muted-foreground" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">Search candidate profiles</h1>
              <p className="text-sm text-muted-foreground">
                Describe the role or skills you&apos;re looking for in plain language.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              {EXAMPLE_QUERIES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => runSearch(example, { limit: 10, numCandidates: 100 })}
                  className="rounded-full border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {turns.map((turn) => (
              <ChatTurn key={turn.id} turn={turn} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <div className="mx-auto w-full max-w-3xl">
        <ChatInput disabled={isSearching} onSubmit={runSearch} />
      </div>
    </div>
  );
}
