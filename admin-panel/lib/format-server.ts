import { stat } from "node:fs/promises";

export async function fileLastModifiedIso(filePath: string): Promise<string | null> {
  try {
    const info = await stat(filePath);
    return new Date(info.mtimeMs).toISOString();
  } catch {
    return null;
  }
}
