<template>
  <header class="hero">
    <q-img src="/logo.svg" class="hero-logo" />
    <div class="hero-text">
      <span class="text-h5 hero-title">Polarsteps Album Generator</span>
      <span class="text-subtitle2 hero-subtitle">
        Turn your trips into beautiful photo albums
      </span>
    </div>
  </header>
</template>

<style scoped>
.hero {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding-bottom: 2.5rem;
  animation: fadeUp 0.5s ease both;
}

.hero-logo {
  width: 5rem;
  height: 5rem;
  flex-shrink: 0;
}

.hero-text {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.hero-title {
  color: var(--text-bright);
}

.hero-subtitle {
  color: var(--text-faint);
}
</style>
