"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Toaster } from "react-hot-toast";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime:            20 * 1000,
            retry:                1,
            refetchOnWindowFocus: true,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 3000,
          style: {
            background: "#1a1d24",
            color:      "#f1f5f9",
            border:     "1px solid #252830",
            fontFamily: "var(--font-syne)",
            fontSize:   "14px",
          },
          success: {
            iconTheme: { primary: "#10b981", secondary: "#064e3b" },
          },
          error: {
            iconTheme: { primary: "#ef4444", secondary: "#450a0a" },
          },
        }}
      />
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}