"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";
import { apiFetch } from "./api";

/**
 * Returns a fetcher bound to the current Clerk session token.
 * The token is attached per request so the backend authorizes and
 * tenant-scopes every call server-side.
 */
export function useApi() {
  const { getToken } = useAuth();

  return useCallback(
    async <T>(path: string, init: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      return apiFetch<T>(path, token, init);
    },
    [getToken],
  );
}
