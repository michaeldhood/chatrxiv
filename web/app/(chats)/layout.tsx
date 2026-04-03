import { ChatBrowserShell } from "@/components/chat-browser-shell";

export default function ChatsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <ChatBrowserShell>{children}</ChatBrowserShell>;
}
