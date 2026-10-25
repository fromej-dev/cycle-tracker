import { format, parseISO, isValid, type Locale } from 'date-fns';
import { enUS, nl } from 'date-fns/locale';

const locales: Record<string, Locale> = { en: enUS, nl };

export function dfLocale(code: string): Locale {
    return locales[code?.split('-')[0]] ?? enUS;
}

/** "Tue 12 Nov" / "di 12 nov" (year appended only when it is not the current year). */
export function formatDay(value: string | Date | null | undefined, localeCode = 'en', withYear = false): string | null {
    if (!value) return null;
    const d = typeof value === 'string' ? parseISO(value) : value;
    if (!isValid(d)) return null;
    const showYear = withYear || d.getFullYear() !== new Date().getFullYear();
    return format(d, showYear ? 'EEE d MMM yyyy' : 'EEE d MMM', { locale: dfLocale(localeCode) }).replace(/\./g, '');
}

/** "12 Nov – 16 Nov" style compact range ("12–16 Nov" when same month). */
export function formatRange(start: string | null | undefined, end: string | null | undefined, localeCode = 'en'): string | null {
    const a = start ? parseISO(start) : null;
    const b = end ? parseISO(end) : null;
    if (!a || !isValid(a)) return null;
    if (!b || !isValid(b)) return formatDay(a, localeCode);
    const loc = dfLocale(localeCode);
    const sameMonth = a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear();
    const yr = b.getFullYear() !== new Date().getFullYear() ? ' yyyy' : '';
    const s = sameMonth ? format(a, 'd', { locale: loc }) : format(a, 'd MMM', { locale: loc });
    // non-breaking spaces: a date range must never wrap in the middle
    return `${s} – ${format(b, 'd MMM' + yr, { locale: loc })}`.replace(/\./g, '').replace(/ /g, '\u00A0');
}

/** Pieces for "between {a} and {b}": ("3", "7 Nov") within one month, ("30 Oct", "2 Nov") across months. */
export function formatBetween(start: string | null | undefined, end: string | null | undefined, localeCode = 'en'): { a: string; b: string } | null {
    const s = start ? parseISO(start) : null;
    const e = end ? parseISO(end) : null;
    if (!s || !e || !isValid(s) || !isValid(e)) return null;
    const loc = dfLocale(localeCode);
    const clean = (x: string) => x.replace(/\./g, '').replace(/ /g, ' ');
    const sameMonth = s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear();
    return {
        a: clean(sameMonth ? format(s, 'd', { locale: loc }) : format(s, 'd MMM', { locale: loc })),
        b: clean(format(e, 'd MMM', { locale: loc })),
    };
}

/** "3 Nov" */
export function formatShort(value: string | Date, localeCode = 'en'): string {
    const d = typeof value === 'string' ? parseISO(value) : value;
    return format(d, 'd MMM', { locale: dfLocale(localeCode) }).replace(/\./g, '');
}
