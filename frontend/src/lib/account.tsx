"use client";

import { useQuery } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { AwsConnection } from "@/lib/types";
import { useApi } from "@/lib/useApi";

/**
 * Tracks which connected AWS account is currently selected. The selection is
 * persisted per browser and exposed to pages so data views stay consistent.
 *
 * Note: data isolation is enforced server-side by tenant. This selector scopes
 * WHICH of the tenant's own connected accounts is shown; it is a UX convenience,
 * not a security boundary.
 */
interface AccountContextValue {
  connections: AwsConnection[];
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string) => void;
  isLoading: boolean;
}

const AccountContext = createContext<AccountContextValue | null>(null);
const STORAGE_KEY = "ccc.selectedAccountId";

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const api = useApi();
  const [selectedAccountId, setSelected] = useState<string | null>(null);

  const connectionsQuery = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });

  const connections = useMemo(
    () =>
      (connectionsQuery.data ?? []).filter(
        (c): c is AwsConnection & { account_id: string } => !!c.account_id,
      ),
    [connectionsQuery.data],
  );

  // Initialise selection from storage or the first connected account.
  useEffect(() => {
    if (connections.length === 0) return;
    const stored =
      typeof window !== "undefined"
        ? window.localStorage.getItem(STORAGE_KEY)
        : null;
    const valid = connections.find((c) => c.account_id === stored);
    setSelected((prev) => prev ?? valid?.account_id ?? connections[0].account_id);
  }, [connections]);

  const setSelectedAccountId = (id: string) => {
    setSelected(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, id);
    }
  };

  const value: AccountContextValue = {
    connections,
    selectedAccountId,
    setSelectedAccountId,
    isLoading: connectionsQuery.isLoading,
  };

  return (
    <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
  );
}

export function useAccounts(): AccountContextValue {
  const ctx = useContext(AccountContext);
  if (!ctx) {
    throw new Error("useAccounts must be used within AccountProvider");
  }
  return ctx;
}
