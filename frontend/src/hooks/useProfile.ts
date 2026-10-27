import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile, profileKeys, updateProfile } from '../api/profile';

/** Pass `enabled = !!user` so the request is not made without a session. */
export function useProfile(enabled: boolean) {
  return useQuery({
    queryKey: profileKeys.profile,
    queryFn: ({ signal }) => getProfile(signal),
    enabled,
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updateProfile,
    onSuccess: (profile) => qc.setQueryData(profileKeys.profile, profile),
  });
}
