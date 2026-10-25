<template>
  <div class="homepage-wrapper">

    <Navbar />

    <section class="hero-section relative text-center overflow-hidden bg-background min-h-[calc(100vh-var(--navbar-height,64px))] flex items-center justify-center p-6">
      <div class="relative z-10 max-w-3xl mx-auto">
        <h1 class="text-4xl sm:text-5xl md:text-6xl text-ink mb-5 font-display leading-tight animate-fade-in-up">
          {{ $t('homepage.hero.title') }} <span class="text-primary">{{ $t('homepage.hero.titleHighlight') }}</span>
        </h1>
        <p class="text-lg sm:text-xl text-ink-soft mb-10 leading-relaxed animate-fade-in-up animation-delay-300">
          {{ $t('homepage.hero.subtitle')}}
        </p>
        <div class="flex flex-col sm:flex-row justify-center items-center animate-fade-in-up animation-delay-600">
            <router-link :to="{ name: 'register' }" class="btn btn-primary w-full sm:w-auto">
              {{ $t('homepage.hero.buttons.register')}}
            </router-link>
            <router-link :to="{ name: 'login' }" class="btn btn-secondary mt-4 sm:mt-0 sm:ml-4 w-full sm:w-auto">
              {{ $t('common.login')}}
            </router-link>
        </div>
      </div>
    </section>

    <section class="features-section py-16 lg:py-24 bg-surface">
      <div class="container mx-auto px-6 text-center">
        <h2 class="text-3xl lg:text-4xl text-ink font-display mb-4"> {{ $t('homepage.features.title')}}</h2>
        <p class="text-lg text-ink-soft mb-12 max-w-2xl mx-auto">{{ $t('homepage.features.subtitle') }}</p>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-12">
          <div class="feature-card bg-primary-soft p-8 rounded-2xl shadow-card hover:shadow-card transition-shadow duration-300">
            <div class="text-primary mb-4">
              <svg class="h-12 w-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
            </div>
            <h3 class="text-xl text-ink font-display mb-2">{{ $t('homepage.features.cards.tracking.title') }}</h3>
            <p class="text-ink-soft">{{ $t('homepage.features.cards.tracking.description') }}</p>
          </div>
          <div class="feature-card bg-luteal-soft p-8 rounded-2xl shadow-card hover:shadow-card transition-shadow duration-300">
            <div class="text-primary mb-4">
              <svg class="h-12 w-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            </div>
            <h3 class="text-xl text-ink font-display mb-2">{{ $t('homepage.features.cards.predictions.title') }}</h3>
            <p class="text-ink-soft">{{ $t('homepage.features.cards.predictions.description') }}</p>
          </div>
          <div class="feature-card bg-fertile-soft p-8 rounded-2xl shadow-card hover:shadow-card transition-shadow duration-300">
            <div class="text-primary mb-4">
              <svg class="h-12 w-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            </div>
            <h3 class="text-xl text-ink font-display mb-2">{{ $t('homepage.features.cards.insights.title') }}</h3>
            <p class="text-ink-soft">{{ $t('homepage.features.cards.insights.description') }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="benefits-section py-16 lg:py-24 bg-background">
      <div class="container mx-auto px-6">
        <div class="text-center mb-12">
          <h2 class="text-3xl lg:text-4xl text-ink font-display mb-4">{{ $t('homepage.benefits.title') }}</h2>
          <p class="text-lg text-ink-soft max-w-2xl mx-auto">{{ $t('homepage.benefits.subtitle') }}</p>
        </div>
        <div class="flex flex-col md:flex-row items-center gap-8 lg:gap-16 mb-12 lg:mb-16">
          <div class="w-full md:w-1/2">
            <img src="/assets/screenshots/planning.png" alt="Visual representing planning" class="rounded-2xl shadow-lg mx-auto">
          </div>
          <div class="w-full md:w-1/2 text-center md:text-left">
            <h3 class="text-2xl text-ink font-display mb-3">{{ $t('homepage.benefits.items.plan.title') }}</h3>
            <p class="text-ink-soft leading-relaxed">{{ $t('homepage.benefits.items.plan.description') }}</p>
          </div>
        </div>
        <div class="flex flex-col md:flex-row-reverse items-center gap-8 lg:gap-16">
          <div class="w-full md:w-1/2">
            <img src="/assets/screenshots/wellbeing.png" alt="Visual representing wellness" class="rounded-2xl shadow-lg mx-auto">
          </div>
          <div class="w-full md:w-1/2 text-center md:text-left">
            <h3 class="text-2xl text-ink font-display mb-3">{{ $t('homepage.benefits.items.wellbeing.title') }}</h3>
            <p class="text-ink-soft leading-relaxed">{{ $t('homepage.benefits.items.wellbeing.description') }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="peek-section py-16 lg:py-24 bg-surface">
      <div class="container mx-auto px-6 text-center">
        <h2 class="text-3xl lg:text-4xl text-ink font-display mb-4">{{ $t('homepage.peek.title') }}</h2>
        <p class="text-lg text-ink-soft mb-12 max-w-2xl mx-auto">{{ $t('homepage.peek.subtitle') }}</p>
        <div class="max-w-4xl mx-auto bg-surface-muted p-6 rounded-2xl shadow-xl">
          <img src="/assets/screenshots/dashboard.png" alt="App dashboard mockup" class="rounded-md">
        </div>
      </div>
    </section>

    <section class="cta-section py-16 lg:py-24 bg-primary text-on-primary">
      <div class="container mx-auto px-6 text-center">
        <h2 class="text-3xl lg:text-4xl font-semibold mb-4">{{ $t('homepage.cta.title') }}</h2>
        <p class="text-lg text-on-primary/80 mb-8 max-w-xl mx-auto">{{ $t('homepage.cta.subtitle') }}</p>
          <router-link :to="{ name: 'register' }" class="btn btn-white">
            {{ $t('homepage.cta.buttons.register') }}
          </router-link>
      </div>
    </section>

    <Footer/>

  </div>
</template>

<script setup lang="ts">
import Navbar from "@/components/Navbar.vue";
import Footer from "@/components/Footer.vue";
</script>

<style scoped>
</style>