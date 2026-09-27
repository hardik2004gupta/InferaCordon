import { Sidebar } from "@/components/app/Sidebar";
import { AppHeader } from "@/components/app/AppHeader";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <AppHeader />
        <main className="flex-1 overflow-y-auto surface-canvas px-4 py-5 lg:px-8 lg:py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
