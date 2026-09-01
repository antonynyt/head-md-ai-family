<script setup>

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

</script>

<template>
    <article lang="en">
        <h2 class="term">{{ word.term }}</h2>
        <p class="part_of_speech">{{word.part_of_speech }}</p>
        <p class="pronunciation italic">{{ word.pronunciation }}</p>
        <p>
            <span class="definition">{{ word.definition }} </span>
            <span class="example italic">{{ word.example }} </span> 
            <span class="saved_at">Added by {{ word.added_by }} on the {{ formatedDate }}</span>
        </p>
    </article>
</template>

<style scoped>

article {
    text-align: justify;
    hyphens: auto;
    break-inside: avoid;
}

.pronunciation {
    hyphens: none;
}

article > * {
    display: inline;
    margin-left: 0.2rem;
}

.definition {
    margin-left: 0.2rem;
}


h2.term {
    text-transform: uppercase;
    font-weight: bold;
    color: var(--accent-color);
    font-size: 1.1rem;
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
    margin-left: 0.2rem;
    font-size: 0.95rem;
}

.definition::before {
    content: '❋';
    color: var(--accent-color);
    font-style: normal;
    margin-right: 0.4rem;
}

</style>