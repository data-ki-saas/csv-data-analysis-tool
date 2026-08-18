import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getSettings,
  HeaderPreset,
  FooterPreset,
  updateFooterPresets,
  updateHeaderPresets,
  updateSettings,
} from "@/lib/api";

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: getSettings });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
    },
  });
}

export function useUpdateHeaderPresets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (presets: HeaderPreset[]) => updateHeaderPresets(presets),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
    },
  });
}

export function useUpdateFooterPresets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (presets: FooterPreset[]) => updateFooterPresets(presets),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
    },
  });
}
