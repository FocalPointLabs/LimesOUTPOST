import { Sidebar } from "@/components/shell/Sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      {/* Left Sidebar */}
      <Sidebar />

      {/* Main Command Area */}
      <main className="flex-1 overflow-y-auto relative">
        {/* Subtle grid — uses .bg-grid from globals so it stays in sync with the palette */}
        <div className="fixed inset-0 pointer-events-none bg-grid" />

        <div className="max-w-7xl mx-auto px-8 py-8 relative z-10">
          {children}
        </div>
      </main>
    </div>
  );
}
