import { type ReactNode } from "react";
import { TopNav } from "./TopNav";

export function AppShell({
  navRight,
  children,
}: {
  navRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="h-screen w-full flex flex-col overflow-hidden bg-bg font-body">
      <TopNav right={navRight} />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1360px] mx-auto px-10 py-9">{children}</div>
      </main>
    </div>
  );
}
