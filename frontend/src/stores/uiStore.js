import { create } from "zustand";
import { persist } from "zustand/middleware";

const MAX_RECENT = 8;

/**
 * Client-only state. Nothing here comes from the API.
 *
 * Deliberately does NOT hold the current user or any auth flag - under cookie
 * auth "am I signed in" is server state, so React Query owns it via /auth/me.
 * Keeping a copy here would give us two sources of truth that drift apart the
 * moment a token expires.
 */
export const useUiStore = create(
  persist(
    (set, get) => ({
      theme: "system",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },

      // Scores are useful while we are still judging result quality, and
      // meaningless to a recruiter. Toggle rather than hard-code.
      showScores: true,
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
