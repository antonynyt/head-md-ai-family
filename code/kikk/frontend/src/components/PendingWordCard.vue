<script setup>
import { computed } from 'vue'

const props = defineProps({
    word: {
        type: Object,
        required: true,
    },
})

const definition = computed(() => {
    if (props.word.definition) {
        return props.word.definition.trim().endsWith('.') ? props.word.definition.trim() : props.word.definition.trim() + '.'
    }
    return ''
})
</script>

<template>
    <article class="pending-word" lang="en">
        <h2 class="term">{{ word.term }}</h2>
        <p><span class="part_of_speech" v-if="word.part_of_speech">{{ word.part_of_speech }}</span> <span class="pronunciation italic" v-if="word.pronunciation">{{ word.pronunciation }}</span> <span class="definition"><span class="text-icon">❋</span> {{ definition }}</span> <span class="example italic">{{ word.example }}</span> <span class="pending-hint"> ✦ awaiting confirmation</span></p>
    </article>
</template>

<style scoped>
.pending-word {
    text-align: justify;
    hyphens: auto;
}

.pending-word > * {
    display: inline;
    margin-left: 0.2rem;
}

h2.term {
    text-transform: uppercase;
    font-weight: bold;
    color: var(--accent-color);
    margin-left: 0;
}

.part_of_speech {
    font-weight: bold;
    margin-left: 0.4rem;
}

.pronunciation {
    hyphens: none;
}

.pronunciation::before {
    content: '<';
    font-weight: bold;
}

.pronunciation::after {
    content: '>';
    font-weight: bold;
}

.text-icon {
    color: var(--accent-color);
    font-style: normal;
}

.pending-hint {
    color: var(--secondary-text-color);
    font-size: 0.85rem;
}
</style>
