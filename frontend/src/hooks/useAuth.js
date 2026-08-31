import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { clearToken, getToken, setToken } from "@/lib/authToken";

export const meKey = ["auth", "me"];

/**
 * The signed-in user, as the server sees it.
 *
 * With no token there is nothing to verify, so this resolves to `null` without
 * a request - the signed-out state is answered locally instead of by a 401.
 * When a token is present the server is still the authority: it re-reads the
 * account on every call, so a deactivated user is rejected even mid-session.
 */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      if (!getToken()) return null;
      return (await api.get("/auth/me")).data;
    },
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
      // Store the token before seeding the user: anything that renders off the
      // back of this cache write will immediately fire authenticated requests.
      setToken(data);
      // The response already contains the user, so seed the cache rather than
      // making the app wait on a second round trip to /auth/me.
      queryClient.setQueryData(meKey, data.user);
    },
  });
}

/**
 * Signing out is entirely local: discard the token and drop every cached
 * response. There is no server call because there would be nothing for it to
 * do - the token is stateless and stays valid until it expires, so the API has
 * no session to end and no revocation list to add it to.
 */
export function useLogout() {
  const queryClient = useQueryClient();
  return () => {
    clearToken();
    queryClient.setQueryData(meKey, null);
    queryClient.clear();
  };
}
