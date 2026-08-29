import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const usersKey = ["users"];

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: usersKey,
    queryFn: async () => (await api.get("/users")).data,
    enabled,
    retry: false,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload) => (await api.post("/users", payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }) => (await api.patch(`/users/${id}`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id) => (await api.delete(`/users/${id}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}
