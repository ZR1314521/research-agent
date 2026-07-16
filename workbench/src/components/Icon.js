// Inline SVG icon set — replaces Unicode dingbats that render as boxes on Windows.
// Each icon is a tiny pure-SVG path; no external dependency, no font fallback issues.

const SIZE = 18;

function icon(viewBox, children) {
  return function IconComponent({ size = SIZE, className, ...props }) {
    return (
      <svg
        width={size}
        height={size}
        viewBox={viewBox}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
        {...props}
      >
        {children}
      </svg>
    );
  };
}

const registry = {
  plus:           icon("0 0 24 24", <path d="M12 5v14M5 12h14" />),
  trash:          icon("0 0 24 24", <><path d="M3 6h18" /><path d="M8 6V4h8v2M19 6l-1 14H6L5 6" /></>),
  search:         icon("0 0 24 24", <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
  chart:          icon("0 0 24 24", <><rect x="3" y="3" width="7" height="18" rx="1" /><rect x="14" y="9" width="7" height="12" rx="1" /></>),
  edit:           icon("0 0 24 24", <path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />),
  check:          icon("0 0 24 24", <path d="M20 6L9 17l-5-5" />),
  x:              icon("0 0 24 24", <><path d="M18 6L6 18" /><path d="M6 6l12 12" /></>),
  pause:          icon("0 0 24 24", <><rect x="5" y="4" width="5" height="16" rx="1" /><rect x="14" y="4" width="5" height="16" rx="1" /></>),
  play:           icon("0 0 24 24", <path d="M6 4l15 8-15 8z" />),
  send:           icon("0 0 24 24", <><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4z" /></>),
  settings:       icon("0 0 24 24", <><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" /></>),
  activity:       icon("0 0 24 24", <polyline points="13 2 3 14 12 14 11 22 21 10 12 10" />),
  clock:          icon("0 0 24 24", <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>),
  palette:        icon("0 0 24 24", <><circle cx="13.5" cy="10.5" r="2.5" /><path d="M12 2a10 10 0 1 0 2 19.8c.7 0 1-.6 1-1.2v-.7c0-.9.7-1.7 1.6-1.7h1.7A7.7 7.7 0 0 0 12 2z" /></>),
  shield:         icon("0 0 24 24", <path d="M12 22s8-4 8-10V6l-8-4-8 4v6c0 6 8 10 8 10z" />),
  checkSquare:    icon("0 0 24 24", <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 12l2 2 4-4" /></>),
  externalLink:   icon("0 0 24 24", <><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></>),
  arrowRight:     icon("0 0 24 24", <><path d="M5 12h14" /><polyline points="12 5 19 12 12 19" /></>),
  chevronUp:      icon("0 0 24 24", <polyline points="18 15 12 9 6 15" />),
  chevronDown:    icon("0 0 24 24", <polyline points="6 9 12 15 18 9" />),
  chevronRight:   icon("0 0 24 24", <polyline points="9 18 15 12 9 6" />),
  zap:            icon("0 0 24 24", <polygon points="13 2 3 14 12 14 11 22 21 10 12 10" />),
  ellipsis:       icon("0 0 24 24", <><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none" /></>),
  circle:         icon("0 0 24 24", <circle cx="12" cy="12" r="8" />),
  dash:           icon("0 0 24 24", <path d="M5 12h14" />),
  warning:        icon("0 0 24 24", <><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></>),
  dot:            icon("0 0 24 24", <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />),
  document:       icon("0 0 24 24", <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></>),
  section:        icon("0 0 24 24", <><path d="M6 8h12M6 12h12M6 16h8" /></>),
};

export default function Icon({ name, size, className }) {
  const Component = registry[name];
  if (!Component) return null;
  return <Component size={size} className={className} />;
}

export { SIZE };
