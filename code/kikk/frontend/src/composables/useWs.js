import { onBeforeUnmount, onMounted, ref } from 'vue'

const RECONNECT_DELAY = 5000

export function useWs(
	host = import.meta.env.VITE_WS_HOST || 'localhost',
	port = Number(import.meta.env.VITE_WS_PORT || 3001),
) {
	const status = ref('connecting')
	const operatorCaption = ref('')
	const words = ref([])
	const lastAddedWord = ref(null)
	const mentionedTerms = ref(null)
	const pendingWord = ref(null)
	const messageHandlers = new Set()

	let socket = null
	let reconnectTimer = null
	let isUnmounted = false
	let lastTurn = null

	// Transcript chunks arrive as soon as Gemini generates the text, well before
	// their audio is actually heard through the speaker. Each chunk carries
	// delay_ms — how long until its audio finishes playing — so we hold it back
	// that long before rendering. pendingAt enforces FIFO order even if two
	// chunks' delays land out of sequence (the playback queue can drain
	// unevenly between messages).
	const pendingTranscriptTimers = new Set()
	let pendingAt = 0

	function clearPendingTranscripts() {
		pendingTranscriptTimers.forEach((timer) => clearTimeout(timer))
		pendingTranscriptTimers.clear()
		pendingAt = 0
	}

	function clearReconnectTimer() {
		if (reconnectTimer) {
			clearTimeout(reconnectTimer)
			reconnectTimer = null
		}
	}

	function scheduleReconnect() {
		if (isUnmounted || reconnectTimer) return

		status.value = 'offline'
		reconnectTimer = setTimeout(() => {
			reconnectTimer = null
			connect()
		}, RECONNECT_DELAY)
	}

	function normalizeTranscriptText(value) {
		return (value || '')
			.replace(/\[(user|model)\]/gi, '')
			.replace(/\s+/g, ' ')
			.trim()
	}

	// Only the operator's own speech is shown, as a single live line: chunks
	// within the same turn are appended (the sentence building word by word),
	// but a fresh operator turn — one that follows the caller talking — replaces
	// whatever was there before instead of piling up a transcript.
	function applyTranscriptChunk(rawText, turn) {
		if (turn === 'model') {
			const text = normalizeTranscriptText(rawText)
			if (text) {
				operatorCaption.value = lastTurn === 'model' ? `${operatorCaption.value} ${text}`.trim() : text
			}
		}
		lastTurn = turn
	}

	function scheduleTranscriptChunk(text, turn, delayMs) {
		const now = Date.now()
		const targetAt = Math.max(now + (delayMs || 0), pendingAt)
		pendingAt = targetAt

		const timer = setTimeout(() => {
			pendingTranscriptTimers.delete(timer)
			applyTranscriptChunk(text, turn)
		}, targetAt - now)
		pendingTranscriptTimers.add(timer)
	}

	function connect() {
		if (isUnmounted || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) {
			return
		}

		status.value = 'connecting'
		socket = new WebSocket(`ws://${host}:${port}`)

		socket.onopen = () => {
			status.value = 'connected'
		}

		socket.onmessage = (event) => {
			let msg

			try {
				msg = JSON.parse(event.data)
			} catch {
				return
			}

			messageHandlers.forEach((handler) => handler(msg))

			switch (msg.type) {
				case 'session:start':
					status.value = 'session active'
					operatorCaption.value = ''
					pendingWord.value = null
					lastTurn = null
					clearPendingTranscripts()
					break

				case 'session:end':
					status.value = 'idle'
					operatorCaption.value = ''
					pendingWord.value = null
					lastTurn = null
					clearPendingTranscripts()
					break

				case 'transcript':
					scheduleTranscriptChunk(msg.text, msg.turn || 'user', msg.delay_ms)
					break

				case 'dictionary:init':
					words.value = msg.words
					break

				case 'word:pending':
					pendingWord.value = msg.word
					break

				case 'word:saved':
					words.value = [...words.value, msg.word]
					lastAddedWord.value = msg.word
					pendingWord.value = null
					break

				case 'word:highlight':
					mentionedTerms.value = Array.isArray(msg.terms) ? msg.terms : []
					break

				case 'session:error':
					status.value = `error: ${msg.message}`
					break
			}
		}

		socket.onclose = () => {
			socket = null
			scheduleReconnect()
		}
	}

	onMounted(connect)

	onBeforeUnmount(() => {
		isUnmounted = true
		clearReconnectTimer()
		clearPendingTranscripts()
		socket?.close()
		socket = null
		messageHandlers.clear()
	})

	function getWords() {
		return words.value
	}

	function onMessage(handler) {
		messageHandlers.add(handler)

		return () => {
			messageHandlers.delete(handler)
		}
	}

	return {
		status,
		operatorCaption,
		words,
		lastAddedWord,
		mentionedTerms,
		pendingWord,
		getWords,
		onMessage,
	}
}
