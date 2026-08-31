import { create } from "zustand";
import { persist } from "zustand/middleware";

const MAX_RECENT = 8;

/**
 * Client-only state. Nothing here comes from the API.
 *
 * Deliberately does NOT hold the current user or any auth flag - "am I signed
 * in" is server state, so React Query owns it via /auth/me and the token lives
 * in @/lib/authToken. Keeping a copy here would give us two sources of truth
 * that drift apart the moment a token expires.
 */
export const useUiStore = create(
  persist(
    (set, get) => ({
      theme: "system",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },

      // Hidden by default: a cosine similarity means nothing to a recruiter and
      // invites ranking arguments it cannot settle. The toggle stays for the
      // times we are judging result quality ourselves.
      showScores: false,
      toggleScores: () => set((s) => ({ showScores: !s.showScores })),

      recentSearches: [],
      addRecentSearch: (query) => {
        const q = query.trim();
        if (!q) return;
        const next = [q, ...get().recentSearches.filter((r) => r !== q)].slice(0, MAX_RECENT);
        set({ recentSearches: next });
      },
      clearRecentSearches: () => set({ recentSearches: [] }),
    }),
    {
      name: "candidate-search-ui",
      // Scores used to default to on, and that choice is already persisted in
      // every browser that has run this app. Without a version bump the new
      // default would never be seen. This is a one-time reset, not a lasting
      // override: toggling still sticks from here on.
      version: 1,
      migrate: (state) => ({ ...state, showScores: false }),
      onRehydrateStorage: () => (state) => applyTheme(state?.theme ?? "system"),
    },
  ),
);

export function applyTheme(theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
