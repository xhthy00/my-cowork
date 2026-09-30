import { create } from "zustand";
import { persist } from "zustand/middleware";

interface IndustryNavigation {
  activeId: string | null;
  routes: Record<string, string>;
  dirty: boolean;
}
export const useIndustryNavigation = create<IndustryNavigation>()(persist((): IndustryNavigation => ({ activeId: null, routes: {}, dirty: false }), {
  name: "my-cowork-industry-navigation",
  partialize: ({ activeId, routes }) => ({ activeId, routes }),
}));

export function leaveIndustryPage(): boolean {
  if (!useIndustryNavigation.getState().dirty) return true;
  if (!window.confirm("业务页面有未保存的内容。仍要离开吗？")) return false;
  useIndustryNavigation.setState({ dirty: false });
  return true;
}
