import { useQuery } from "@tanstack/react-query";
import { listDatasets } from "@/lib/api";

export function useDatasets() {
  return useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
}
