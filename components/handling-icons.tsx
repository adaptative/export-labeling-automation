export function HandlingIcons({ size = "default" }: { size?: "default" | "small" }) {
  const iconSize = size === "small" ? "w-5 h-5" : "w-6 h-6";
  
  return (
    <div className="flex items-end gap-1">
      {/* This Side Up */}
      <div className="flex flex-col items-center">
        <svg className={iconSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 19V5M5 12l7-7 7 7" />
          <path d="M12 19V5M5 12l7-7 7 7" transform="translate(0, -4)" />
        </svg>
        <span className="text-[6px] font-semibold uppercase text-center leading-tight mt-0.5">
          This Side<br />Up
        </span>
      </div>
      
      {/* Fragile */}
      <div className="flex flex-col items-center">
        <svg className={iconSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M8 2v4l-2 2v6a2 2 0 002 2h8a2 2 0 002-2V8l-2-2V2" />
          <path d="M12 6v6" />
          <path d="M9.5 8.5l5 3" />
          <path d="M14.5 8.5l-5 3" />
          <path d="M6 22h12" />
          <path d="M8 18l-2 4" />
          <path d="M16 18l2 4" />
        </svg>
        <span className="text-[6px] font-semibold uppercase text-center leading-tight mt-0.5">
          Fragile
        </span>
      </div>
      
      {/* Keep Dry */}
      <div className="flex flex-col items-center">
        <svg className={iconSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M12 2v1" />
          <path d="M4 12h1" />
          <path d="M19 12h1" />
          <path d="M6.34 6.34l.7.7" />
          <path d="M17.66 6.34l-.7.7" />
          <path d="M5 17c0-2.76 3.13-5 7-5s7 2.24 7 5" />
          <path d="M5 17h14" />
          <path d="M7 20h10" />
          <path d="M8 20v2" />
          <path d="M16 20v2" />
        </svg>
        <span className="text-[6px] font-semibold uppercase text-center leading-tight mt-0.5">
          Keep<br />Dry
        </span>
      </div>
    </div>
  );
}
