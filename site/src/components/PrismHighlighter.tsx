import { Highlight, themes } from "prism-react-renderer";
import { cn } from "../lib/cn";

/**
 * Split out so the syntax highlighter only downloads when a code block is near
 * the viewport. CodeBlock renders plain, already-escaped text until then.
 */
export default function PrismHighlighter({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  return (
    <Highlight theme={themes.vsDark} code={code} language={language}>
      {({ className, style, tokens, getLineProps, getTokenProps }) => (
        <pre
          className={cn("scroll-slim overflow-x-auto p-4 text-[12.5px] leading-6", className)}
          style={{ ...style, background: "transparent" }}
        >
          {tokens.map((line, lineIndex) => {
            const lineProps = getLineProps({ line });
            return (
              <div key={lineIndex} {...lineProps}>
                {line.map((token, tokenIndex) => (
                  <span key={tokenIndex} {...getTokenProps({ token })} />
                ))}
              </div>
            );
          })}
        </pre>
      )}
    </Highlight>
  );
}
