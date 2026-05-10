import CodeMirror from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { useTheme } from "@/components/theme-provider";

export default function StrategyEditor({
  value,
  onChange,
  readOnly,
  height = "500px",
}: {
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  height?: string;
}) {
  const { resolved } = useTheme();
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <CodeMirror
        value={value}
        height={height}
        theme={resolved === "dark" ? "dark" : "light"}
        extensions={[yaml()]}
        onChange={(v) => onChange(v)}
        readOnly={!!readOnly}
        basicSetup={{
          lineNumbers: true,
          highlightActiveLine: true,
          foldGutter: true,
        }}
      />
    </div>
  );
}
