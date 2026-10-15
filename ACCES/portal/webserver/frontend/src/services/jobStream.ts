import { BASE_URL } from "./api";
import type { JobStatus } from "../types";
import { api } from "./api";

export function streamJobLog(jobId: string, onLine: (line: string) => void): () => void {
  const source = new EventSource(`${BASE_URL}/api/jobs/${jobId}/stream`);
  source.onmessage = (event) => onLine(event.data);
  source.onerror = () => source.close();
  return () => source.close();
}

/** Polls a job until it reaches SUCCESS or FAILED. Used for short-lived
 * jobs (device list/install/logcat, tool check) where a full SSE log
 * stream is overkill — the frontend just wants the final result. */
export function pollJobUntilDone(
  jobId: string,
  { intervalMs = 1000, timeoutMs = 120_000 }: { intervalMs?: number; timeoutMs?: number } = {}
): Promise<JobStatus> {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const status = await api.getJob(jobId);
        if (status.status === "SUCCESS" || status.status === "FAILED") {
          resolve(status);
          return;
        }
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Job ${jobId} timed out after ${timeoutMs}ms`));
          return;
        }
        setTimeout(tick, intervalMs);
      } catch (err) {
        reject(err);
      }
    };
    tick();
  });
}
