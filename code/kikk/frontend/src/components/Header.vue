<script setup>

</script>

<template>
  <header>
    <h1>Familect Dictionary</h1>
  </header>
</template>

<style scoped>

header {
    width: calc(100% - var(--side-gap) * 2);
    max-width: 1280px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 1em;
    padding: 5rem 0 0 0;
    padding-bottom: 2rem;
    text-transform: uppercase;
}

h1 {
  font-size: 1.5rem;
}

</style>