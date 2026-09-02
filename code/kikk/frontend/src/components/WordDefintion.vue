<script setup>
import { computed } from 'vue'

const props = defineProps({
    word: {
        type: Object,
        required: true
    }
})

const formatedDate = new Date(props.word.saved_at).toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
}).replaceAll('/', '.').replace(',', ' at ')

//test if last char is a dot otherwise add a dot
const definition = computed(() => {
    if (props.word.definition) {
        return props.word.definition.trim().endsWith('.') ? props.word.definition.trim() : props.word.definition.trim() + '.'
    }
    return ''
})

</script>

<template>
    <article lang="en" tabindex="0">
        <h2 class="term">{{ word.term }}</h2>
        <p><span class="part_of_speech" v-if="word.part_of_speech">{{ word.part_of_speech }}</span> <span class="pronunciation italic" v-if="word.pronunciation">{{ word.pronunciation }}</span> <span class="definition"><span class="text-icon">❋</span> {{ definition }}</span> <span class="example italic">{{ word.example }}</span> <span class="saved_at"> ✦ Added by <span class="italic">{{ word.added_by }}</span> on the {{ formatedDate }}</span></p>
    </article>
</template>

<style scoped>

article {
    text-align: justify;
    hyphens: auto;
    break-inside: avoid;
}

article:focus {
    outline: 2px solid var(--accent-color);
    outline-offset: 0.8rem;
}

.pronunciation {
    hyphens: none;
}

article > * {
    display: inline;
    margin-left: 0.2rem;
}

.part_of_speech {
    margin-left: 0.4rem;
}

h2.term {
    text-transform: uppercase;
    font-weight: bold;
    color: var(--accent-color);
    margin-left: 0;
}

.part_of_speech {
    font-weight: bold;
}

.pronunciation::before {
    content: '<';
    font-weight: bold;
}

.pronunciation::after {
    content: '>';
    font-weight: bold;
}

.saved_at {
    color: var(--secondary-text-color);
    font-size: 0.95rem;
}

.text-icon {
    color: var(--accent-color);
    font-style: normal;
}

/* .definition::before {
    content: '❋';
    color: var(--accent-color);
    font-style: normal;
    margin-right: 0.4rem;
} */

</style>