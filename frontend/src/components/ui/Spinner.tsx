interface Props {
  size?: number;
  class?: string;
}

/** The dots family used across the legacy UI, kept identical. */
export default function Spinner(props: Props) {
  const size = () => props.size ?? 14;
  return (
    <span
      class={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${props.class ?? ""}`}
      style={{ width: `${size()}px`, height: `${size()}px` }}
      aria-label="加载中"
    />
  );
}
