import { AuthGuard } from "@/components/AuthGuard";
import { Nav } from "@/components/Nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="min-h-screen">
        <Nav />
        <main className="mx-auto max-w-7xl px-5 py-6">{children}</main>
      </div>
    </AuthGuard>
  );
}
