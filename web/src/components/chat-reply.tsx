import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Model text is untrusted: no HTML, remote images, or custom URL transforms. */
export function ChatReply({ text }: { text: string }) {
  return <div className="chat-reply min-w-0 break-words" data-testid="chat-reply">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
      img: () => null,
      a: ({ children, href }) => href ? <a href={href} target="_blank" rel="noopener noreferrer" className="underline">{children}</a> : <span>{children}</span>,
      table: ({ children }) => <div className="max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label="Response table"><table>{children}</table></div>,
    }}>{text}</Markdown>
  </div>;
}
