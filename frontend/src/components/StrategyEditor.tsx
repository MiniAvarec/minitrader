import CodeMirror from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";

export default function StrategyEditor({
  value,
  onChange,
  readOnly,
}: {
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
}) {
  return (
    <CodeMirror
      value={value}
      height="500px"
      theme="dark"
      extensions={[yaml()]}
      onChange={(v) => onChange(v)}
      readOnly={!!readOnly}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: true,
        foldGutter: true,
      }}
    />
  );
}
