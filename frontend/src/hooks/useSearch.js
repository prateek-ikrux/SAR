import { keepPreviousData, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Search is a POST, but it is a read. Modelling it as a query (not a mutation)
 * is what gives us caching, and lets Prev/Next land instantly - the API keeps a
 * pool per query, so page 2 comes back in a couple of milliseconds.
 */
export function useSearch({ query, page, pageSize, collapse }, options = {}) {
  return useQuery({
    queryKey: ["search", { query, page, pageSize, collapse }],
    queryFn: async () => {
      // No mode here: ENN vs ANN is an app-wide setting an admin controls, so
      // the server decides. The response reports which mode actually ran.
      const { data } = await api.post("/search", {
        query,
        page,
        page_size: pageSize,
        collapse_duplicates: collapse,
      });
      return data;
    },
    enabled: Boolean(query),
    // Keeps the previous page on screen while the next one loads, instead of
    // blanking the list for the ~1s a query takes. This shows old data during
    // the fetch; it never serves old data as the answer.
    placeholderData: keepPreviousData,
    // Nothing is cached. Every search - including repeating the same text -
    // goes to the server, so results are always current.
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    retry: false,
    ...options,
  });
}

export function useProfile(id) {
  return useQuery({
    queryKey: ["profile", id],
    queryFn: async () => (await api.get(`/profiles/${id}`)).data,
    enabled: Boolean(id),
    staleTime: 10 * 60_000,
    retry: false,
  });
}

/**
 * Resume links are short-lived presigned URLs, so they are fetched on demand
 * rather than cached. Roughly one profile in five has no PDF in the bucket and
 * comes back 404 - the caller is expected to surface that, not swallow it.
 */
export function useResumeLink() {
  return useMutation({
    mutationFn: async (id) => (await api.get(`/profiles/${id}/resume`)).data,
  });
}

/** Warm the cache for a profile the user is about to open. */
export function usePrefetchProfile() {
  const queryClient = useQueryClient();
  return (id) =>
    queryClient.prefetchQuery({
      queryKey: ["profile", id],
      queryFn: async () => (await api.get(`/profiles/${id}`)).data,
      staleTime: 10 * 60_000,
    });
}
