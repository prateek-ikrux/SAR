import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const settingsKey = ["settings"];

/** Admin only. Recruiters never read this - the search response tells them which mode ran. */
export function useSettings(enabled = true) {
  return useQuery({
    queryKey: settingsKey,
    queryFn: async () => (await api.get("/settings")).data,
    enabled,
    retry: false,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload) => (await api.put("/settings", payload)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKey, data);
      // Cached results were produced under the old mode, so drop them.
      queryClient.removeQueries({ queryKey: ["search"] });
    },
  });
}
