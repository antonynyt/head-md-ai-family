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
  <div class="callout" :class="{ 'speaking': active }">
    <p v-if="active">{{ caption || 'Listening…' }}</p>
    <p v-else>The Familect Dictionary stores your vocabulary.</p>
  </div>
</template>

<style scoped>

.callout {
    border: 3px solid var(--accent-color);
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
    z-index: 999;
}

.speaking {
    animation: blink 500ms infinite alternate ease-out;
    background: var(--background-noise) var(--first-level-background-color);
}

.speaking.callout::after {
    background: var(--background-noise), linear-gradient(to bottom, var(--first-level-background-color) 30%, transparent 30%);
}

@keyframes blink {
    0% { box-shadow: 0 0 0 0 var(--accent-color); }
    100% { box-shadow: 0 0 0px 3px var(--accent-color); }
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