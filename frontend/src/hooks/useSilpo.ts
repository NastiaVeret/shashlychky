import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteSilpoConnection,
  getSilpoConnection,
  silpoKeys,
  startSilpoConnection,
  type SilpoConnection,
} from '../api/silpo';

/** Pass `enabled = !!user` so the request is not made without a session. */
export function useSilpoConnection(enabled: boolean) {
  return useQuery({
    queryKey: silpoKeys.connection,
    queryFn: ({ signal }) => getSilpoConnection(signal),
    enabled,
  });
}

/** On success the whole page leaves for Silpo's login; it comes back to /profile?silpo=... */
export function useConnectSilpo() {
  return useMutation({
    mutationFn: startSilpoConnection,
    onSuccess: ({ authorize_url }) => window.location.assign(authorize_url),
  });
}

export function useDisconnectSilpo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteSilpoConnection,
    onSuccess: () => {
      const disconnected: SilpoConnection = { connected: false, connected_at: null };
      qc.setQueryData(silpoKeys.connection, disconnected);
    },
  });
}
