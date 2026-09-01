import { onBeforeUnmount, onMounted, ref } from 'vue'

const RECONNECT_DELAY = 5000

export function useWs(
	host = import.meta.env.VITE_WS_HOST || 'localhost',
	port = Number(import.meta.env.VITE_WS_PORT || 3001),
) {
	const status = ref('connecting')
	const transcript = ref('')
	const transcriptHistory = ref([])
	const words = ref([])
	const messageHandlers = new Set()

	let socket = null
	let reconnectTimer = null
	let isUnmounted = false

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

	function appendTranscriptChunk(rawText, turn = 'user') {
		const text = normalizeTranscriptText(rawText)
		if (!text) {
			return
		}

		const lastEntry = transcriptHistory.value[transcriptHistory.value.length - 1]
		if (lastEntry && lastEntry.turn === turn) {
			lastEntry.text = `${lastEntry.text} ${text}`.trim()
		} else {
			transcriptHistory.value.push({
				id: `${Date.now()}-${Math.random()}`,
				turn,
				text,
			})
		}

		if (transcriptHistory.value.length > 4) {
			transcriptHistory.value = transcriptHistory.value.slice(-4)
		}

		transcript.value = transcriptHistory.value.map((entry) => entry.text).join(' ')
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
					transcript.value = ''
					transcriptHistory.value = []
					break

				case 'session:end':
					status.value = 'idle'
					break

				case 'transcript':
					appendTranscriptChunk(msg.text, msg.turn || 'user')
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
			socket = null
			scheduleReconnect()
		}
	}

	onMounted(connect)

	onBeforeUnmount(() => {
		isUnmounted = true
		clearReconnectTimer()
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

	return { status, transcript, transcriptHistory, words, getWords, onMessage }
}
