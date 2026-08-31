<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

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
</script>

<template>
  <main style="font-family: sans-serif; padding: 2rem; max-width: 700px; margin: 0 auto;">
    <h1>Familect</h1>

    <p><strong>Status:</strong> {{ status }}</p>

    <section style="margin-top: 1rem;">
      <h2>Transcript</h2>
      <p>{{ transcript || 'Waiting for speech...' }}</p>
    </section>

    <section style="margin-top: 1rem;">
      <h2>Saved words</h2>
      <p>{{ words.length }}</p>
      <ul>
        <li v-for="word in words" :key="word.saved_at || word.term">
          {{ word.term }} — {{ word.definition }}
        </li>
      </ul>
    </section>
  </main>
</template>
