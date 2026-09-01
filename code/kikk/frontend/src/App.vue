<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import Header from './components/Header.vue'
import Footer from './components/Footer.vue'
import WordDefintion from './components/WordDefintion.vue'

const status = ref('connecting')
const transcript = ref('')
const words = ref([])

let socket = null

onMounted(() => {
    const host = "172.28.194.67"
    socket = new WebSocket(`ws://${host}:3001`)

    socket.onopen = () => {
        status.value = 'connected'
    }

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data)

        switch (msg.type) {
            case 'session:start':
                status.value = 'session active'
                break

            case 'session:end':
                status.value = 'idle'
                break

            case 'transcript':
                transcript.value = msg.text
                break

            case 'dictionary:init':
                words.value = msg.words
                break

            case 'word:saved':
                words.value = [...words.value, msg.word]
                break

            case 'session:error':
                status.value = `error: ${msg.message}`
                break
        }
    }

    socket.onclose = () => {
        status.value = 'reconnecting...'
    }
})

onBeforeUnmount(() => {
    socket?.close()
})

words.value.push({
    term: 'ZOZO',
    pronunciation: 'ˈzō-zō',
    part_of_speech: 'n.m.',
    definition: 'A person given to foolish, clownish, or intentionally ignorant behavior.',
    example: 'The class clown was known as a complete zozo whenever lessons became too serious.',
    added_by: 'David',
    saved_at: '2026-05-23T09:21:01.661836+00:00'
},
)

for (let i = 0; i < 20; i++) {
    words.value.push({
        term: `TERM ${i}`,
        pronunciation: `pronun ${i}`,
        part_of_speech: 'adj.',
        definition: `A dialect or language that is unique to a particular family or household. ${i}.`,
        example: `Example usage of term ${i}.`,
        added_by: `User ${i}`,
        saved_at: new Date().toISOString()
    })
}

</script>

<template>
    <Header />
    <main>
        <div class="dico">
            <WordDefintion :word="word" v-for="word in words" :key="word.saved_at || word.term" />
            <div class="spacer"></div>
        </div>
    </main>
    <Footer/>
</template>

<style scoped>
main {
    width: calc(100% - var(--side-gap) * 2);
    margin: 0 auto;
    margin-top: 1rem;
    border: 1.5px solid var(--border-color);
    border-radius: 0.5rem;
    box-sizing: border-box;
    overflow: hidden;
    display: flex;
}

main::-webkit-scrollbar, .dico::-webkit-scrollbar {
  display: none;
}

.dico {
    position: relative;
    column-count: 2;
    column-gap: 2.5rem;
    padding: 2rem 2rem;
    overflow-x: auto;
    overflow-y: hidden;

    scroll-snap-type: x mandatory;
    overscroll-behavior-x:none;
    scroll-padding: 0 2rem;
    
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
