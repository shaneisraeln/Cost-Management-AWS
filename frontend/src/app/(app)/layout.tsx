import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { AccountSelector } from "@/components/AccountSelector";
import { Sidebar } from "@/components/Sidebar";
import { AccountProvider } from "@/lib/account";

// Authenticated dashboard pages are rendered per-request, never statically
// prerendered at build time (they depend on the signed-in user/org).
export const dynamic = "force-dynamic";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AccountProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1">
          <header className="flex items-center justify-between border-b border-white/10 px-6 py-3">
            <div className="flex items-center gap-4">
              <OrganizationSwitcher hidePersonal />
              <AccountSelector />
            </div>
            <UserButton />
          </header>
          <main className="p-6">{children}</main>
        </div>
      </div>
    </AccountProvider>
  );
}
