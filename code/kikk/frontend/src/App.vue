<script setup>
import { nextTick, reactive, computed, watch, ref } from 'vue'
import Callout from './components/Callout.vue'
import Header from './components/Header.vue'
import Modal from './components/Modal.vue'
import WordDefintion from './components/WordDefintion.vue'
import { useWs } from './composables/useWs.js'

const ADDED_HIGHLIGHT_MS = 15000
const MENTIONED_HIGHLIGHT_MS = 10000
const RING_IDLE_MS     = 80_000;
const RING_DURATION_MS = 30_000;

const { status, operatorCaption, words, lastAddedWord, mentionedTerms, pendingWord } = useWs()

// Debug: open the app with ?debug in the URL, then tap a word definition to
// preview it in the pending-word modal. Tap the modal (or press Escape) to close.
const DEBUG = new URLSearchParams(window.location.search).has('debug')
const debugPendingWord = ref(null)
const modalWord = computed(() => pendingWord.value ?? debugPendingWord.value)

function onWordTap(word) {
    if (DEBUG) debugPendingWord.value = word
}

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

watch(mentionedTerms, async (terms) => {
    if (!terms?.length) return

    let lastKey = null
    for (const term of terms) {
        const key = (term || '').trim().toLowerCase()
        highlightWord(key, MENTIONED_HIGHLIGHT_MS)
        if (wordEls.has(key)) lastKey = key
    }

    await nextTick()
    wordEls.get(lastKey)?.scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' })
})

    // ── Ring audio ────────────────────────────────────────────────────────────
    const ring = new Audio('/output3-1.mp3');
    ring.loop  = true;

    function startRing() {
      ring.currentTime = 0;
      ring.play().catch(e => console.warn('[ring] play failed:', e));
      console.log('[ring] started');
    }

    function stopRing() {
      ring.pause();
      ring.currentTime = 0;
      console.log('[ring] stopped');
    }

    // ── Ring scheduler (client-side) ──────────────────────────────────────────
    let idleTimer     = null;
    let durationTimer = null;

    function armRing() {
      clearRingTimers();
      idleTimer = setTimeout(() => {
        startRing();
        durationTimer = setTimeout(() => {
          stopRing();
          armRing();
        }, RING_DURATION_MS);
      }, RING_IDLE_MS);
      console.log(`[ring] armed — ringing in ${RING_IDLE_MS / 1000}s`);
    }

    armRing()

    function cancelRing() {
      clearRingTimers();
      stopRing();
    }

    function clearRingTimers() {
      clearTimeout(idleTimer);
      clearTimeout(durationTimer);
      idleTimer     = null;
      durationTimer = null;
    }

    // cancel ring on session active
    watch(status, (newStatus) => {
      if (newStatus === 'session active') {
        cancelRing();
      } else {
        armRing();
      }
    });
</script>

<template>
    <Header />
    <Callout :active="status === 'session active'" :caption="operatorCaption" />
    <main>
        <div class="dico">
            <WordDefintion v-for="word in newestFirst" :key="wordKey(word)" :word="word"
                :class="{ highlight: highlightedKeys.has(wordKey(word)) }"
                :ref="(el) => setWordEl(wordKey(word), el)"
                @click="onWordTap(word)" />
            <div class="spacer"></div>
        </div>
    </main>
    <Modal :pending-word="modalWord" @close="debugPendingWord = null" />
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
