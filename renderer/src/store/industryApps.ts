import { create } from "zustand";

type Catalog = Awaited<ReturnType<typeof window.api.industryList>>;

// Keep the catalog across page unmounts, but never persist runtime generations
// across desktop launches.
export const useIndustryApps = create<{
  catalog: Catalog | null;
  loading: boolean;
  error: string;
}>(() => ({ catalog: null, loading: false, error: "" }));

let pending: Promise<Catalog | undefined> | undefined;

export function refreshIndustryApps(force = false): Promise<Catalog | undefined> {
  if (pending && !force) return pending;
  useIndustryApps.setState({ loading: true, error: "" });
  const request = Promise.resolve().then(() => window.api.industryList()).then((catalog) => {
    // A refresh after an installation or runtime change supersedes older reads.
    if (pending !== request) return;
    useIndustryApps.setState({ catalog });
    return catalog;
  }).catch((cause) => {
    if (pending === request) {
      useIndustryApps.setState({ error: cause instanceof Error ? cause.message : String(cause) });
    }
    return undefined;
  }).finally(() => {
    if (pending === request) {
      pending = undefined;
      useIndustryApps.setState({ loading: false });
    }
  });
  pending = request;
  return request;
}
