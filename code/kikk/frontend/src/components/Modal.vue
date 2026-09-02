<script setup>
import { ref, watch } from 'vue'
import PendingWordCard from './PendingWordCard.vue'

const props = defineProps({
    pendingWord: {
        type: Object,
        default: null,
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
    () => props.pendingWord,
    (word) => {
        if (word) {
            openDialog()
            return
        }

        closeDialog()
    },
    { immediate: true },
)
</script>

<template>
    <dialog ref="dialogRef" class="confirm-dialog">
        <div class="dialog-body" v-if="pendingWord">
            <PendingWordCard :word="pendingWord" />
        </div>
    </dialog>
</template>

<style scoped>
.confirm-dialog {
    max-width: 400px;
    padding: 0;
    background: var(--background-noise) var(--background-color);

    border: 2px solid var(--secondary-text-color);
    border-radius: 5px;
    box-sizing: border-box;
}

.confirm-dialog::focus {
    outline: none;
}

.dialog-body {
    padding: 0.75rem 1rem 1rem;
}
</style>
