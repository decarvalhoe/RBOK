export type StatusVariant = 'success' | 'error' | 'info';

const VARIANT_STYLES: Record<StatusVariant, string> = {
  success: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  error: 'bg-rose-100 text-rose-800 ring-1 ring-rose-200',
  info: 'bg-sky-100 text-sky-800 ring-1 ring-sky-200',
};

export type StatusBadgeProps = {
  label: string;
  variant?: StatusVariant;
  className?: string;
};

export function StatusBadge({ label, variant = 'info', className }: StatusBadgeProps): JSX.Element {
  const classes = [
    'inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide',
    VARIANT_STYLES[variant],
  ];

  if (className) {
    classes.push(className);
  }

  return (
    <span
      className={classes.join(' ')}
      role="status"
      aria-label={`${variant} status: ${label}`}
    >
      {label}
    </span>
  );
}

export default StatusBadge;
