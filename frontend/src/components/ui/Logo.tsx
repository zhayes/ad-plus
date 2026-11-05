interface Props {
  size?: number;
  class?: string;
}

/** The real app icon (assets/icon.svg), so the mark never drifts from the bundle. */
export default function Logo(props: Props) {
  const size = () => props.size ?? 22;
  return (
    <img
      src="/icon.svg"
      alt="Ad+"
      width={size()}
      height={size()}
      class={`block rounded-[7px] ${props.class ?? ""}`}
      style={{ width: `${size()}px`, height: `${size()}px` }}
    />
  );
}
