import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { deleteMe, getMe, login, logout, meKeys, register, type UserRead } from '../api/auth';
import { profileKeys } from '../api/profile';
import { recipeKeys } from '../api/recipes';

/** `data` is `null` when not logged in; `undefined` only while the first request is pending. */
export function useMe() {
  return useQuery({
    queryKey: meKeys.me,
    queryFn: ({ signal }) => getMe(signal),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

function onLoggedIn(qc: QueryClient, user: UserRead) {
  qc.setQueryData(meKeys.me, user);
  void qc.invalidateQueries({ queryKey: profileKeys.profile });
  void qc.invalidateQueries({ queryKey: recipeKeys.mine });
}

/** Also called from the QueryClient caches when any request answers 401: the session is gone. */
export function onLoggedOut(qc: QueryClient) {
  qc.setQueryData(meKeys.me, null);
  qc.removeQueries({ queryKey: profileKeys.profile });
  qc.removeQueries({ queryKey: recipeKeys.mine });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: login,
    onSuccess: (user) => onLoggedIn(qc, user),
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: register,
    onSuccess: (user) => onLoggedIn(qc, user),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: logout,
    // The cookie is httpOnly, so the client cannot clear it; whether or not the server answered,
    // forgetting the user locally is what the person expects after pressing "Вийти".
    onSettled: () => onLoggedOut(qc),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteMe,
    onSuccess: () => onLoggedOut(qc),
  });
}
