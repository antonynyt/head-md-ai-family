<script setup>
defineProps({
    active: {
        type: Boolean,
        default: false,
    },
    caption: {
        type: String,
        default: '',
    },
})
</script>

<template>
  <div class="callout">
    <p v-if="active">{{ caption || 'Listening…' }}</p>
    <p v-else>The Familect Dictionary stores your vocabulary.</p>
  </div>
</template>

<style scoped>

.callout {
    border: 2px solid var(--secondary-text-color);
    border-radius: 5px;
    width: calc(100% - var(--side-gap) * 2);
    max-width: 1280px;
    height: 4em;
    overflow-y: scroll;
    overflow-x: hidden;
    display: flex;
    align-items: end;
    /* justify-content: center;
    text-align: center; */
    margin: 0rem auto 2rem auto;
    padding: 1rem 2rem;
    box-sizing: border-box;
    /* background: var(--background-noise) var(--first-level-background-color); */
    position: relative;
    color: var(--secondary-text-color);
}

.callout::-webkit-scrollbar {
    display: none;
}

.callout::after {
    content: '';
    display: flex;
    justify-content: center;
    position: absolute;
    top: 0;
    left: 0;
    width: 200%;
    height: 100%;
    background: var(--background-noise), linear-gradient(to bottom, var(--background-color) 30%, transparent 30%);
}

</style>