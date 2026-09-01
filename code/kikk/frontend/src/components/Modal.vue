<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  items: {
    type: Array,
    default: () => [],
  },
})

const dialogRef = ref(null)

function openDialog() {
  const dialog = dialogRef.value

  if (!dialog || dialog.open) {
    return
  }

  dialog.showModal()
}

function closeDialog() {
  const dialog = dialogRef.value

  if (!dialog || !dialog.open) {
    return
  }

  dialog.close()
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      openDialog()
      return
    }

    closeDialog()
  },
  { immediate: true },
)
</script>

<template>
  <dialog ref="dialogRef" class="transcript-dialog">
    <div class="dialog-header">
      <h2>Transcript history</h2>
      <button type="button" class="close-button" @click="closeDialog">Close</button>
    </div>

    <div class="dialog-body" v-if="items.length">
      <article v-for="entry in [...items].reverse()" :key="entry.id || entry.text" class="entry" :class="entry.turn">
        <span class="speaker">{{ entry.turn === 'model' ? 'AI' : 'You' }}</span>
        <p>{{ entry.text }}</p>
      </article>
    </div>

    <div v-else class="empty-state">
      <p>No transcript yet.</p>
    </div>
  </dialog>
</template>

<style scoped>
.transcript-dialog {
  width: min(90vw, 600px);
  max-height: 70vh;
  padding: 0;
  border: 1px solid var(--border-color);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #ddd;
}

.dialog-header h2 {
  margin: 0;
  font-size: 1rem;
}

.close-button {
  padding: 0.25rem 0.5rem;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 1rem 1rem;
  overflow-y: auto;
}

.entry {
  padding: 0.5rem 0.75rem;
  border: 1px solid #eee;
}

.speaker {
  display: block;
  font-size: 0.7rem;
  text-transform: uppercase;
}

.entry p {
  margin: 0.25rem 0 0;
  white-space: pre-wrap;
}

.empty-state {
  padding: 1rem;
  text-align: center;
}
</style>
