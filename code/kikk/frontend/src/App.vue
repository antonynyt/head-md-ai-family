<script setup>
import Header from './components/Header.vue'
import Modal from './components/Modal.vue'
import WordDefintion from './components/WordDefintion.vue'
import { useWs } from './composables/useWs.js'

const { status, transcriptHistory, words } = useWs()
</script>

<template>
    <Header />
    <main>
        <div class="dico">
            <WordDefintion :word="word" v-for="word in words" :key="word.saved_at || word.term" />
            <div class="spacer"></div>
        </div>
    </main>
    <Modal :open="status === 'session active'" :items="transcriptHistory" />
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
    padding: 1rem 0rem;
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
