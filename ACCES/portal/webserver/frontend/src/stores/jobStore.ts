import { create } from "zustand";

interface JobStore {
  activeJobId: string | null;
  activeJobType: string | null;
  progress: number;
  status: "IDLE" | "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";
  startJob: (jobId: string, jobType: string) => void;
  setProgress: (progress: number) => void;
  setStatus: (status: JobStore["status"]) => void;
  reset: () => void;
}

export const useJobStore = create<JobStore>((set) => ({
  activeJobId: null,
  activeJobType: null,
  progress: 0,
  status: "IDLE",
  startJob: (jobId, jobType) =>
    set({ activeJobId: jobId, activeJobType: jobType, progress: 0, status: "QUEUED" }),
  setProgress: (progress) => set({ progress }),
  setStatus: (status) => set({ status }),
  reset: () => set({ activeJobId: null, activeJobType: null, progress: 0, status: "IDLE" }),
}));
