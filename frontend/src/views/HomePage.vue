<template>
  <div class="homepage">
    <Navbar sections />

    <!-- HERO -->
    <section class="hero relative overflow-hidden">
      <div class="hero-glow" aria-hidden="true"></div>
      <div class="relative mx-auto max-w-6xl px-4 sm:px-6 pt-12 pb-16 lg:pt-20 lg:pb-24 grid lg:grid-cols-[1.05fr_1fr] gap-12 lg:gap-8 items-center">
        <div class="text-center lg:text-left">
          <p class="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm font-medium text-ink-soft animate-fade-in-up">
            <span class="h-2 w-2 rounded-full bg-fertile" aria-hidden="true"></span>
            {{ $t('homepage.hero.eyebrow') }}
          </p>
          <h1 class="hero-title font-display text-ink mt-6 animate-fade-in-up">
            {{ $t('homepage.hero.title') }}
            <span class="block italic text-primary">{{ $t('homepage.hero.titleHighlight') }}</span>
          </h1>
          <p class="mt-6 text-lg sm:text-xl text-ink-soft leading-relaxed max-w-xl mx-auto lg:mx-0 animate-fade-in-up animation-delay-300">
            {{ $t('homepage.hero.subtitle') }}
          </p>
          <div class="mt-9 flex flex-col sm:flex-row gap-3 justify-center lg:justify-start animate-fade-in-up animation-delay-300">
            <router-link :to="{ name: 'register' }" class="btn btn-primary">
              {{ $t('homepage.hero.primary') }}
              <ArrowRightIcon class="h-5 w-5 ml-2" aria-hidden="true" />
            </router-link>
            <router-link :to="{ name: 'login' }" class="btn btn-secondary">
              {{ $t('homepage.hero.secondary') }}
            </router-link>
          </div>
          <p class="mt-5 text-sm text-ink-soft flex items-center gap-2 justify-center lg:justify-start animate-fade-in-up animation-delay-600">
            <DevicePhoneMobileIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
            {{ $t('homepage.hero.note') }}
          </p>
        </div>

        <div class="hero-phones relative mx-auto w-full max-w-[22rem] sm:max-w-[26rem] lg:max-w-none animate-fade-in-up animation-delay-300">
          <PhoneFrame
              class="hero-phone-back hidden sm:block"
              :src="shot('calendar')"
              :alt="$t('homepage.hero.calendarAlt')"
          />
          <PhoneFrame
              class="hero-phone-front"
              :src="shot(isDark ? 'today-dark' : 'today')"
              :alt="$t('homepage.hero.todayAlt')"
              eager
          />
        </div>
      </div>
    </section>

    <!-- WHY -->
    <section class="py-20 lg:py-28 bg-surface border-y border-line">
      <div class="mx-auto max-w-6xl px-4 sm:px-6">
        <div class="max-w-2xl mx-auto text-center reveal" v-reveal>
          <h2 class="section-heading font-display text-ink">{{ $t('homepage.pillars.title') }}</h2>
          <p class="mt-4 text-lg text-ink-soft leading-relaxed">{{ $t('homepage.pillars.subtitle') }}</p>
        </div>
        <div class="mt-14 grid gap-6 md:grid-cols-3">
          <div v-for="(p, i) in pillars" :key="p.key"
               class="rounded-[1.75rem] border border-line bg-background p-7 reveal" v-reveal
               :style="{ transitionDelay: `${i * 80}ms` }">
            <div class="h-12 w-12 rounded-2xl flex items-center justify-center" :class="p.tint">
              <component :is="p.icon" class="h-6 w-6" aria-hidden="true" />
            </div>
            <h3 class="mt-5 font-display text-xl text-ink">{{ $t(`homepage.pillars.${p.key}.title`) }}</h3>
            <p class="mt-2 text-ink-soft leading-relaxed">{{ $t(`homepage.pillars.${p.key}.text`) }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- FEATURES -->
    <section id="features" class="scroll-mt-16 py-20 lg:py-28">
      <div class="mx-auto max-w-6xl px-4 sm:px-6 space-y-24 lg:space-y-32">
        <div v-for="(f, i) in features" :key="f.key"
             class="grid lg:grid-cols-2 gap-10 lg:gap-20 items-center">
          <div class="feature-visual reveal" v-reveal :class="[f.tint, i % 2 ? 'lg:order-2' : '']">
            <PhoneFrame class="w-[15.5rem] sm:w-[17rem] mx-auto" :src="shot(f.key === 'today' ? (isDark ? 'today' : 'today-dark') : f.shot)" :alt="featureAlt(f.key)" />
          </div>
          <div class="reveal" v-reveal>
            <p class="eyebrow-label" :class="f.ink">{{ $t(`homepage.features.${f.key}.eyebrow`) }}</p>
            <h2 class="mt-3 section-heading font-display text-ink">{{ $t(`homepage.features.${f.key}.title`) }}</h2>
            <p class="mt-5 text-lg text-ink-soft leading-relaxed">{{ $t(`homepage.features.${f.key}.text`) }}</p>
            <ul class="mt-7 space-y-3">
              <li v-for="n in 3" :key="n" class="flex gap-3 text-ink">
                <span class="mt-0.5 h-6 w-6 shrink-0 rounded-full flex items-center justify-center" :class="f.tint">
                  <CheckIcon class="h-4 w-4" :class="f.ink" aria-hidden="true" />
                </span>
                {{ $t(`homepage.features.${f.key}.p${n}`) }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- EXTRAS -->
    <section class="py-20 lg:py-28 bg-surface border-y border-line">
      <div class="mx-auto max-w-6xl px-4 sm:px-6">
        <div class="max-w-2xl mx-auto text-center reveal" v-reveal>
          <h2 class="section-heading font-display text-ink">{{ $t('homepage.extras.title') }}</h2>
          <p class="mt-4 text-lg text-ink-soft">{{ $t('homepage.extras.subtitle') }}</p>
        </div>
        <div class="mt-14 grid gap-x-10 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="x in extras" :key="x.key" class="flex gap-4 reveal" v-reveal>
            <div class="h-11 w-11 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center">
              <component :is="x.icon" class="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h3 class="font-semibold text-ink">{{ $t(`homepage.extras.${x.key}.title`) }}</h3>
              <p class="mt-1 text-ink-soft leading-relaxed">{{ $t(`homepage.extras.${x.key}.text`) }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- PRIVACY -->
    <section id="privacy" class="scroll-mt-16 py-20 lg:py-28">
      <div class="mx-auto max-w-6xl px-4 sm:px-6">
        <div class="privacy-band rounded-[2rem] p-8 sm:p-12 lg:p-16 grid lg:grid-cols-[1.2fr_1fr] gap-12 reveal" v-reveal>
          <div>
            <p class="eyebrow-label privacy-accent flex items-center gap-2">
              <LockClosedIcon class="h-4 w-4" aria-hidden="true" />
              {{ $t('homepage.privacy.eyebrow') }}
            </p>
            <h2 class="mt-3 section-heading font-display">{{ $t('homepage.privacy.title') }}</h2>
            <p class="mt-5 text-lg privacy-soft leading-relaxed">{{ $t('homepage.privacy.text') }}</p>
            <ul class="mt-8 space-y-3.5">
              <li v-for="n in 4" :key="n" class="flex gap-3">
                <ShieldCheckIcon class="h-6 w-6 shrink-0 privacy-accent" aria-hidden="true" />
                {{ $t(`homepage.privacy.p${n}`) }}
              </li>
            </ul>
          </div>
          <div class="privacy-card rounded-[1.5rem] p-7 sm:p-8 self-start">
            <CodeBracketIcon class="h-8 w-8 privacy-accent" aria-hidden="true" />
            <h3 class="mt-4 font-display text-2xl">{{ $t('homepage.privacy.selfTitle') }}</h3>
            <p class="mt-3 privacy-soft leading-relaxed">{{ $t('homepage.privacy.selfText') }}</p>
            <a :href="repoUrl" class="mt-6 inline-flex items-center gap-2 font-semibold privacy-accent hover:underline underline-offset-4">
              {{ $t('homepage.privacy.selfLink') }}
              <ArrowRightIcon class="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </div>
      </div>
    </section>

    <!-- FAQ -->
    <section id="faq" class="scroll-mt-16 pb-20 lg:pb-28">
      <div class="mx-auto max-w-3xl px-4 sm:px-6">
        <h2 class="section-heading font-display text-ink text-center reveal" v-reveal>{{ $t('homepage.faq.title') }}</h2>
        <div class="mt-10 border-t border-line">
          <details v-for="q in faq" :key="q" class="faq-item group border-b border-line">
            <summary class="flex items-center justify-between gap-4 py-5 cursor-pointer list-none text-lg font-semibold text-ink">
              {{ $t(`homepage.faq.${q}.q`) }}
              <ChevronDownIcon class="h-5 w-5 shrink-0 text-ink-soft transition-transform group-open:rotate-180" aria-hidden="true" />
            </summary>
            <p class="pb-6 -mt-1 text-ink-soft leading-relaxed">{{ $t(`homepage.faq.${q}.a`) }}</p>
          </details>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="pb-20 lg:pb-28">
      <div class="mx-auto max-w-6xl px-4 sm:px-6">
        <div class="cta-card relative overflow-hidden rounded-[2rem] bg-primary text-on-primary px-6 py-14 sm:px-12 sm:py-20 text-center reveal" v-reveal>
          <h2 class="section-heading font-display">{{ $t('homepage.cta.title') }}</h2>
          <p class="mt-4 text-lg max-w-xl mx-auto opacity-90">{{ $t('homepage.cta.subtitle') }}</p>
          <router-link :to="{ name: 'register' }" class="btn btn-white mt-8">
            {{ $t('homepage.cta.button') }}
            <ArrowRightIcon class="h-5 w-5 ml-2" aria-hidden="true" />
          </router-link>
        </div>
      </div>
    </section>

    <Footer />
  </div>
</template>

<script setup lang="ts">
import type { Directive } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  ArrowRightIcon,
  CalendarDaysIcon,
  CheckIcon,
  ChevronDownIcon,
  CodeBracketIcon,
  DevicePhoneMobileIcon,
  DocumentTextIcon,
  HeartIcon,
  HomeModernIcon,
  LanguageIcon,
  LockClosedIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/vue/24/outline';
import Navbar from "@/components/Navbar.vue";
import Footer from "@/components/Footer.vue";
import PhoneFrame from "@/components/PhoneFrame.vue";
import { useDarkMode } from '@/composables/useDarkMode';

const { locale, t } = useI18n();
const { isDark } = useDarkMode();

const repoUrl = 'https://github.com/fromej-dev/cycle-tracker';

// real screenshots of the app, one set per locale (public/assets/screenshots/<locale>/)
const shotLocales = ['en', 'nl'];
const shot = (name: string) =>
  `/assets/screenshots/${shotLocales.includes(locale.value) ? locale.value : 'en'}/${name}.webp`;

const pillars = [
  { key: 'honest', icon: SparklesIcon, tint: 'bg-period-soft text-period-ink' },
  { key: 'private', icon: LockClosedIcon, tint: 'bg-luteal-soft text-luteal-ink' },
  { key: 'plans', icon: CalendarDaysIcon, tint: 'bg-fertile-soft text-fertile-ink' },
];

// the Today row shows the other theme than the hero, so the two don't repeat
const features = [
  { key: 'today', shot: 'today', tint: 'bg-period-soft', ink: 'text-period-ink' },
  { key: 'calendar', shot: 'calendar', tint: 'bg-fertile-soft', ink: 'text-fertile-ink' },
  { key: 'plan', shot: 'plan', tint: 'bg-luteal-soft', ink: 'text-luteal-ink' },
  { key: 'history', shot: 'history', tint: 'bg-primary-soft', ink: 'text-primary' },
];
const featureAlt = (key: string) =>
  key === 'today' ? t('homepage.hero.todayAlt')
  : key === 'calendar' ? t('homepage.hero.calendarAlt')
  : t(`homepage.features.${key}.alt`);

const extras = [
  { key: 'calendar', icon: CalendarDaysIcon },
  { key: 'partner', icon: HeartIcon },
  { key: 'doctor', icon: DocumentTextIcon },
  { key: 'app', icon: DevicePhoneMobileIcon },
  { key: 'home', icon: HomeModernIcon },
  { key: 'theme', icon: LanguageIcon },
];

const faq = ['free', 'accuracy', 'irregular', 'contraception', 'data', 'phone'];

// fade sections in once as they scroll into view (CSS keeps them visible without JS / with reduced motion)
const vReveal: Directive<HTMLElement> = {
  mounted(el) {
    if (!('IntersectionObserver' in window)) return;
    el.classList.add('reveal-pending');
    const io = new IntersectionObserver((entries) => {
      if (entries.some(e => e.isIntersecting)) {
        el.classList.remove('reveal-pending');
        io.disconnect();
      }
    }, { rootMargin: '0px 0px -10% 0px' });
    io.observe(el);
    (el as any)._revealIo = io;
  },
  unmounted(el) {
    (el as any)._revealIo?.disconnect();
  },
};
</script>

<style scoped>
.hero-title {
  font-size: clamp(2.75rem, 7vw, 4.75rem);
  line-height: 1.02;
  letter-spacing: -0.025em;
  font-variation-settings: "SOFT" 60, "opsz" 144;
}
.section-heading {
  font-size: clamp(2rem, 4.2vw, 3rem);
  line-height: 1.08;
  letter-spacing: -0.025em;
}
.eyebrow-label {
  font-size: 0.8125rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

/* soft phase-coloured light behind the hero */
.hero-glow {
  position: absolute;
  inset: -20% -10% auto -10%;
  height: 120%;
  background:
    radial-gradient(40% 45% at 78% 35%, color-mix(in srgb, var(--color-period) 16%, transparent), transparent 70%),
    radial-gradient(35% 40% at 92% 75%, color-mix(in srgb, var(--color-fertile) 14%, transparent), transparent 70%),
    radial-gradient(40% 40% at 10% 10%, color-mix(in srgb, var(--color-luteal) 10%, transparent), transparent 70%);
  pointer-events: none;
}

/* two overlapping phones: Today in front, Calendar tilted behind */
.hero-phones { aspect-ratio: 1 / 1.25; }
.hero-phone-front {
  position: absolute;
  width: 62%;
  left: 50%;
  top: 0;
  transform: translateX(-50%);
  z-index: 2;
}
.hero-phone-back {
  position: absolute;
  width: 54%;
  right: -2%;
  top: 9%;
  transform: rotate(7deg);
  z-index: 1;
  opacity: 0.95;
}
@media (min-width: 640px) {
  .hero-phone-front { left: 6%; transform: rotate(-3deg); }
}
@media (max-width: 639px) {
  .hero-phones { aspect-ratio: auto; }
  .hero-phone-front { position: relative; width: 78%; margin: 0 auto; left: auto; transform: none; }
}

.feature-visual {
  border-radius: 2rem;
  padding: 3rem 1.5rem;
}
@media (min-width: 640px) {
  .feature-visual { padding: 3.5rem 2rem; }
}

/* deep plum band in light mode, a raised surface in dark mode */
.privacy-band { background: #2B2029; color: #FAF6F2; }
.privacy-soft { color: #D9CCD3; }
.privacy-accent { color: #F6A4BB; }
.privacy-card { background: rgb(255 255 255 / 0.06); border: 1px solid rgb(255 255 255 / 0.1); }
:global(.dark) .privacy-band { background: var(--color-surface); color: var(--color-ink); border: 1px solid var(--color-line); }
:global(.dark) .privacy-soft { color: var(--color-ink-soft); }
:global(.dark) .privacy-accent { color: var(--color-primary); }
:global(.dark) .privacy-card { background: var(--color-surface-muted); border-color: var(--color-line); }

.cta-card::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(50% 80% at 0% 0%, rgb(255 255 255 / 0.14), transparent 60%),
    radial-gradient(40% 70% at 100% 100%, rgb(0 0 0 / 0.12), transparent 60%);
  pointer-events: none;
}
.cta-card > * { position: relative; }

.faq-item summary::-webkit-details-marker { display: none; }

.reveal { transition: opacity 0.6s ease-out, transform 0.6s ease-out; }
.reveal.reveal-pending { opacity: 0; transform: translateY(16px); }
@media (prefers-reduced-motion: reduce) {
  .reveal.reveal-pending { opacity: 1; transform: none; }
}
</style>
