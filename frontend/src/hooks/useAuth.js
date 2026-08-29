import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const meKey = ["auth", "me"];

/**
 * The signed-in user, as the server sees it.
 *
 * A 401 here is the normal signed-out state, not an error worth retrying - the
 * API has no refresh endpoint, so a failure means "show the sign-in screen".
 */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => (await api.get("/auth/me")).data,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useRequestCode() {
  return useMutation({
    mutationFn: async (email) => (await api.post("/auth/request-code", { email })).data,
  });
}

export function useVerifyCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ email, code }) =>
      (await api.post("/auth/verify-code", { email, code })).data,
    onSuccess: (data) => {
      // The response already contains the user, so seed the cache rather than
      // making the app wait on a second round trip to /auth/me.
      queryClient.setQueryData(meKey, data.user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post("/auth/logout")).data,
    onSettled: () => {
      queryClient.setQueryData(meKey, null);
      queryClient.clear();
    },
  });
}
