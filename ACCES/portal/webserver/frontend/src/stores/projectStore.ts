import { create } from "zustand";
import type { Project } from "../types";

interface ProjectStore {
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;
  logLines: string[];
  appendLog: (line: string) => void;
  clearLog: () => void;
  selectedFilePath: string | null;
  selectedLine: number | null;
  setSelectedFilePath: (path: string | null, line?: number | null) => void;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  currentProject: null,
  setCurrentProject: (project) => set({ currentProject: project }),
  logLines: [],
  appendLog: (line) => set((state) => ({ logLines: [...state.logLines, line].slice(-2000) })),
  clearLog: () => set({ logLines: [] }),
  selectedFilePath: null,
  selectedLine: null,
  setSelectedFilePath: (path, line = null) => set({ selectedFilePath: path, selectedLine: path ? line : null }),
}));
