<script setup>
import { computed, nextTick, watch } from 'vue'
import Callout from './components/Callout.vue'
import Header from './components/Header.vue'
import Modal from './components/Modal.vue'
import WordDefintion from './components/WordDefintion.vue'
import { useWs } from './composables/useWs.js'

const { status, operatorCaption, words, lastAddedWord, pendingWord } = useWs()

const newestFirst = computed(() => [...words.value].reverse())
const wordKey = (word) => word.saved_at || word.term

const wordEls = new Map()
function setWordEl(key, componentInstance) {
    if (componentInstance) {
        wordEls.set(key, componentInstance.$el)
    } else {
        wordEls.delete(key)
    }
}

watch(lastAddedWord, async (word) => {
    if (!word) return
    await nextTick()
    wordEls.get(wordKey(word))?.scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' })
})
</script>

<template>
    <Header />
    <Callout :active="status === 'session active'" :caption="operatorCaption" />
    <main>
        <div class="dico">
            <WordDefintion v-for="word in newestFirst" :key="wordKey(word)" :word="word"
                :ref="(el) => setWordEl(wordKey(word), el)" />
            <div class="spacer"></div>
        </div>
    </main>
    <Modal :pending-word="pendingWord" />
</template>

<style scoped>
main {
    width: calc(100% - var(--side-gap) * 2);
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
    column-gap: 2rem;
    padding: 2rem 0rem;
    overflow-x: auto;
    overflow-y: hidden;

    scroll-snap-type: x mandatory;
    overscroll-behavior-x:none;
    /* scroll-padding: 0 2rem; */

    box-sizing:border-box;
}

.spacer {
    height: 100%;
    width: 2rem;
}

article {
    margin-bottom: 1.5rem;
    scroll-snap-align: start;
}


</style>
