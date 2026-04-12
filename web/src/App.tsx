import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/app-layout";
import { BoardPage } from "@/components/board/board-page";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

function Router() {
  const match = window.location.pathname.match(/^\/board\/(\d+)/);
  if (match) return <BoardPage boardId={Number(match[1])} />;
  return <AppLayout />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router />
    </QueryClientProvider>
  );
}
