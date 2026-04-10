export function VaseWithHandles({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 110"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {/* Vase body bottom */}
      <ellipse cx="50" cy="95" rx="28" ry="6" />
      {/* Left side curve */}
      <path d="M22 95 C22 70, 28 55, 35 45 C38 40, 40 30, 40 25" />
      {/* Right side curve */}
      <path d="M78 95 C78 70, 72 55, 65 45 C62 40, 60 30, 60 25" />
      {/* Rim */}
      <ellipse cx="50" cy="22" rx="12" ry="4" />
      {/* Rim connectors */}
      <line x1="38" y1="22" x2="40" y2="25" />
      <line x1="62" y1="22" x2="60" y2="25" />
      {/* Left handle */}
      <path d="M22 60 C10 55, 8 70, 22 78" strokeWidth="1.5" />
      {/* Right handle */}
      <path d="M78 60 C90 55, 92 70, 78 78" strokeWidth="1.5" />
    </svg>
  );
}
