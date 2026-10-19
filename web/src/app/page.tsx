import { Suspense } from "react";
import { ChatTab } from "./chat-tab";

export default function Home() {
  return (
    <Suspense>
      <ChatTab />
    </Suspense>
  );
}
