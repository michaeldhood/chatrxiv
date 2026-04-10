export default function ChatsHomePage() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center p-8 text-center lg:min-h-[calc(100vh-12rem)]">
      <div className="max-w-md space-y-3">
        <h2 className="text-lg font-semibold text-foreground">
          Select a chat
        </h2>
        <p className="text-sm text-muted-foreground">
          Choose a conversation from the list on the left to read it here. On
          small screens, open the chat list with the Chats button above.
        </p>
      </div>
    </div>
  );
}
