import Providers from "./providers";

export const metadata = {
  title: "PlanForge",
  description: "Turn one line into a build-ready spec",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#fafafa",
          color: "#1a1a1a",
        }}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
