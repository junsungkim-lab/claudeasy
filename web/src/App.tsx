import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/app-layout";
import { BoardPage } from "@/components/board/board-page";
import { SettingsPage } from "@/components/settings/settings-page";
import { Header } from "@/components/layout/header";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

function Router() {
  const path = window.location.pathname;
  const boardMatch = path.match(/^\/board\/(\d+)/);
  if (boardMatch) return <BoardPage boardId={Number(boardMatch[1])} />;
  if (path === "/settings") return (
    <div className="flex flex-col h-screen">
      <Header />
      <SettingsPage />
    </div>
  );
  return <AppLayout />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router />
    </QueryClientProvider>
  );
}
