<script setup>
import { nextTick, reactive, computed, watch } from 'vue'
import Callout from './components/Callout.vue'
import Header from './components/Header.vue'
import Modal from './components/Modal.vue'
import WordDefintion from './components/WordDefintion.vue'
import { useWs } from './composables/useWs.js'

const ADDED_HIGHLIGHT_MS = 15000
const MENTIONED_HIGHLIGHT_MS = 10000

const { status, operatorCaption, words, lastAddedWord, mentionedTerms, pendingWord } = useWs()

const newestFirst = computed(() => [...words.value].reverse())
// Terms are unique (the dictionary rejects duplicates case-insensitively), so a
// normalized term doubles as a stable id — no need for a separate id field.
const wordKey = (word) => (word.term || '').trim().toLowerCase()

const wordEls = new Map()
function setWordEl(key, componentInstance) {
    if (componentInstance) {
        wordEls.set(key, componentInstance.$el)
    } else {
        wordEls.delete(key)
    }
}

// Several words can be highlighted at once (a freshly added one, several the
// operator just mentioned), each fading out independently on its own timer.
const highlightedKeys = reactive(new Set())
const highlightTimers = new Map()

function highlightWord(key, durationMs) {
    if (!key) return
    highlightedKeys.add(key)
    clearTimeout(highlightTimers.get(key))
    highlightTimers.set(key, setTimeout(() => {
        highlightedKeys.delete(key)
        highlightTimers.delete(key)
    }, durationMs))
}

watch(lastAddedWord, async (word) => {
    if (!word) return

    const key = wordKey(word)
    highlightWord(key, ADDED_HIGHLIGHT_MS)

    await nextTick()
    wordEls.get(key)?.scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' })
})

watch(mentionedTerms, (terms) => {
    for (const term of terms || []) {
        highlightWord((term || '').trim().toLowerCase(), MENTIONED_HIGHLIGHT_MS)
    }
})
</script>

<template>
    <Header />
    <Callout :active="status === 'session active'" :caption="operatorCaption" />
    <main>
        <div class="dico">
            <WordDefintion v-for="word in newestFirst" :key="wordKey(word)" :word="word"
                :class="{ highlight: highlightedKeys.has(wordKey(word)) }"
                :ref="(el) => setWordEl(wordKey(word), el)" />
            <div class="spacer"></div>
        </div>
    </main>
    <Modal :pending-word="pendingWord" />
</template>

<style scoped>
main {
    /* width: calc(100% - var(--side-gap) * 2 + 4rem); */
    width: 100%;
    margin: 0 auto;
    /* border: 1.5px solid var(--border-color); */
    border-radius: 0.5rem;
    box-sizing: border-box;
    overflow: hidden;
    display: flex;
    flex-grow: 1;
    /* background: var(--background-noise) var(--first-level-background-color); */
    margin-bottom: 2rem;
}

main::-webkit-scrollbar, .dico::-webkit-scrollbar {
  display: none;
}

.dico {
    position: relative;
    column-count: 2;
    padding: 1.2rem calc(var(--side-gap) - 0.5rem);
    overflow-x: auto;
    overflow-y: hidden;

    scroll-snap-type: x mandatory;
    overscroll-behavior-x:none;
    scroll-padding: 0 calc(var(--side-gap) - 0.5rem);

    box-sizing:border-box;
}

.spacer {
    height: 100%;
    width: 2rem;
}

article {
    /* margin-bottom: 1.5rem; */
    scroll-snap-align: start;
}


</style>
