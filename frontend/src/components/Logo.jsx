export default function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#ff6a1a" />
      <path d="M10 7h8l5 5v13H10z" fill="#fff" fillOpacity=".95" />
      <path d="M18 7v5h5z" fill="#ffb48a" />
      <rect x="13" y="15" width="7" height="1.8" rx=".9" fill="#ff6a1a" />
      <rect x="13" y="19" width="7" height="1.8" rx=".9" fill="#ff6a1a" />
    </svg>
  )
}
