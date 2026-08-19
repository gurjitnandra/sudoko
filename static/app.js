const boardElement = document.getElementById('sudoku-board');
const boardOverlay = document.getElementById('board-overlay');
const boardEmptyMessage = document.getElementById('board-empty-message');
const statusBar = document.getElementById('status-bar');
const sessionStatus = document.getElementById('session-status');
const numberPad = document.getElementById('number-pad');
const boardControls = document.getElementById('board-controls');

const joinForm = document.getElementById('join-form');
const joinNameInput = document.getElementById('join-name');
const joinSessionInput = document.getElementById('join-session-id');
const hostForm = document.getElementById('host-form');
const hostNameInput = document.getElementById('host-name');
const hostDifficultySelect = document.getElementById('host-difficulty');

const sessionInfoSection = document.getElementById('session-info');
const sessionIdDisplay = document.getElementById('session-id-display');
const scoreboardSection = document.getElementById('scoreboard');
const scoreList = document.getElementById('score-list');
const joinSection = document.getElementById('join-section');
const hostSection = document.getElementById('host-section');
const leaveButton = document.getElementById('leave-btn');
const layoutElement = document.querySelector('.layout');
const mistakeCounterElement = document.getElementById('mistake-counter');
const boardEliminatedMessage = document.getElementById('board-eliminated-message');
const chatPanel = document.querySelector('.chat-panel');
const chatLogElement = document.getElementById('chat-log');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const emojiBar = document.getElementById('emoji-bar');
const lossBanner = document.getElementById('loss-banner');
const restartContainer = document.getElementById('restart-container');
const restartButton = document.getElementById('restart-button');
const chatHeading = document.getElementById('chat-heading');

if (restartContainer) {
    restartContainer.hidden = true;
}

if (restartButton) {
    restartButton.disabled = true;
}

let currentSessionId = null;
let currentPlayer = null;
let boardState = [];
let givens = [];
let claims = [];
let selectedCell = null;
let pollingInterval = null;
let sessionRefreshInterval = null;
let sessionRefreshDisabled = false; // set once we know there is no login session
const SESSION_REFRESH_INTERVAL = 15 * 60 * 1000; // 15 minutes
const POLLING_INTERVAL = 5000; // 5 seconds
let isFetching = false;
let chatLog = [];
let mistakeLimit = 3;
let isEliminated = false;
let lastChatId = null;
let latestPlayersSnapshot = [];
let latestStateSnapshot = null;
let currentSessionDifficulty = 'easy';

const playerColorCache = new Map();
const activeSelections = new Map();
let lastSentSelectionKey = null;

function withAlpha(hex, alpha) {
    if (!hex) {
        return `rgba(242, 169, 0, ${alpha})`;
    }

    let stripped = hex.trim();
    if (stripped.startsWith('#')) {
        stripped = stripped.slice(1);
    }

    if (stripped.length === 3) {
        stripped = stripped.split('').map((ch) => ch + ch).join('');
    }

    if (stripped.length !== 6) {
        return `rgba(242, 169, 0, ${alpha})`;
    }

    const r = parseInt(stripped.slice(0, 2), 16);
    const g = parseInt(stripped.slice(2, 4), 16);
    const b = parseInt(stripped.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getActivePlayerColor() {
    return currentPlayer?.color || '#f2a900';
}

function canInteractWithBoard() {
    return Boolean(currentSessionId && currentPlayer && !isEliminated);
}

function updateControlsAvailability() {
    const shouldDisable = !canInteractWithBoard();
    numberPad.querySelectorAll('.number-btn').forEach((btn) => {
        btn.disabled = shouldDisable;
        btn.classList.toggle('is-disabled', shouldDisable);
    });
}

function updateOverlayVisibility() {
    const hasSession = Boolean(currentSessionId);
    if (!boardOverlay) return;

    if (!hasSession) {
        boardOverlay.hidden = false;
        if (boardEmptyMessage) boardEmptyMessage.hidden = false;
        if (boardEliminatedMessage) boardEliminatedMessage.hidden = true;
        boardElement.dataset.eliminated = 'false';
        return;
    }

    if (isEliminated) {
        boardOverlay.hidden = false;
        if (boardEmptyMessage) boardEmptyMessage.hidden = true;
        if (boardEliminatedMessage) boardEliminatedMessage.hidden = false;
        boardElement.dataset.eliminated = 'true';
    } else {
        boardOverlay.hidden = true;
        if (boardEmptyMessage) boardEmptyMessage.hidden = true;
        if (boardEliminatedMessage) boardEliminatedMessage.hidden = true;
        boardElement.dataset.eliminated = 'false';
    }
}

function updateMistakeDisplay(mistakes = 0) {
    if (!mistakeCounterElement) return;
    mistakeCounterElement.textContent = `Mistakes: ${mistakes} / ${mistakeLimit}`;
    mistakeCounterElement.dataset.state = isEliminated ? 'eliminated' : 'active';
}

function updateChatAvailability() {
    const canChat = Boolean(currentSessionId && currentPlayer);
    if (chatPanel) {
        chatPanel.hidden = !canChat;
        chatPanel.classList.toggle('chat-disabled', !canChat);
    }
    if (chatInput) {
        chatInput.disabled = !canChat;
        if (!canChat) {
            chatInput.value = '';
        }
    }
    if (chatForm) {
        chatForm.dataset.disabled = (!canChat).toString();
    }
    if (emojiBar) {
        emojiBar.dataset.disabled = (!canChat).toString();
        emojiBar.querySelectorAll('button').forEach((btn) => {
            btn.disabled = !canChat;
        });
    }
}

function selectionKey(row, col) {
    if (row === null || row === undefined || col === null || col === undefined) {
        return 'none';
    }
    return `${row}-${col}`;
}

async function announceSelection(row, col) {
    if (!currentSessionId || !currentPlayer || isEliminated) return;

    const normalizedRow = Number.isInteger(row) ? row : null;
    const normalizedCol = Number.isInteger(col) ? col : null;
    const nextKey = selectionKey(normalizedRow, normalizedCol);

    if (nextKey === lastSentSelectionKey) {
        return;
    }

    try {
        const response = await fetch(`/api/session/${currentSessionId}/selection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playerId: currentPlayer.id,
                row: normalizedRow,
                col: normalizedCol,
            }),
        });

        if (!response.ok) {
            lastSentSelectionKey = null;
            return;
        }

        lastSentSelectionKey = nextKey;
    } catch (error) {
        lastSentSelectionKey = null;
        console.error(error);
    }
}

function toggleLobbyState(isInSession) {
    joinSection.hidden = isInSession;
    hostSection.hidden = isInSession;
    joinSection.style.display = isInSession ? 'none' : '';
    hostSection.style.display = isInSession ? 'none' : '';
    leaveButton.disabled = !isInSession;
    boardEmptyMessage.hidden = isInSession;
    if (layoutElement) {
        layoutElement.classList.toggle('in-session', isInSession);
    }

    if (isInSession) {
        sessionInfoSection.hidden = false;
    }

    updateChatAvailability();
    updateOverlayVisibility();
}

function resetClientState() {
    stopPolling();
    sessionRefreshDisabled = false;
    currentSessionId = null;
    currentPlayer = null;
    boardState = [];
    givens = [];
    claims = [];
    selectedCell = null;
    playerColorCache.clear();
    activeSelections.clear();
    lastSentSelectionKey = null;
    chatLog = [];
    lastChatId = null;
    mistakeLimit = 3;
    isEliminated = false;
    latestPlayersSnapshot = [];
    latestStateSnapshot = null;
    currentSessionDifficulty = 'easy';

    sessionStatus.textContent = 'Join or host a session to begin.';
    sessionIdDisplay.textContent = '----';
    scoreList.innerHTML = '';
    scoreboardSection.hidden = true;
    sessionInfoSection.hidden = true;
    boardOverlay.hidden = false;
    boardControls.hidden = true;
    boardEmptyMessage.hidden = false;
    if (boardEliminatedMessage) {
        boardEliminatedMessage.hidden = true;
    }
    boardElement.dataset.eliminated = 'false';

    if (mistakeCounterElement) {
        mistakeCounterElement.textContent = 'Mistakes: 0 / 3';
        mistakeCounterElement.dataset.state = 'active';
    }

    document.documentElement.style.removeProperty('--player-highlight');

    document.querySelectorAll('.cell').forEach((cell) => {
        cell.dataset.selected = 'false';
        cell.dataset.given = 'false';
        cell.dataset.editable = 'true';
        cell.dataset.claimed = 'false';
        cell.style.removeProperty('--cell-claim-color');
        cell.style.removeProperty('--cell-claim-border');
        const valueDisplay = cell.querySelector('.cell-value');
        valueDisplay.textContent = '';
        valueDisplay.style.color = '#fefefe';
    });

    if (chatLogElement) {
        chatLogElement.innerHTML = '';
    }

    if (chatHeading) {
        chatHeading.textContent = 'Hello there!';
    }

    if (lossBanner) {
        lossBanner.hidden = true;
    }

    if (restartContainer) {
        restartContainer.hidden = true;
        restartContainer.classList.add('d-none');
    }

    toggleLobbyState(false);
    updateControlsAvailability();
    updateChatAvailability();
    updateOverlayVisibility();
}

function createNumberButtons() {
    numberPad.innerHTML = '';
    for (let value = 1; value <= 9; value += 1) {
        const button = document.createElement('button');
        button.className = 'number-btn';
        button.textContent = value.toString();
        button.dataset.value = value.toString();
        button.addEventListener('click', () => submitMove(value));
        numberPad.appendChild(button);
    }
    updateControlsAvailability();
}

function updateChatHeading(players = latestPlayersSnapshot) {
    if (!chatHeading) return;
    const name = currentPlayer?.name?.trim();
    if (name) {
        chatHeading.textContent = `Hello ${name}`;
        return;
    }

    const playerId = currentPlayer?.id;
    if (playerId) {
        const match = players.find((p) => p.id === playerId);
        if (match?.name) {
            chatHeading.textContent = `Hello ${match.name.trim()}`;
            return;
        }
    }

    chatHeading.textContent = 'Hello there!';
}

function initBoard() {
    boardElement.innerHTML = '';
    for (let row = 0; row < 9; row += 1) {
        for (let col = 0; col < 9; col += 1) {
            const template = document.getElementById('cell-template');
            const cellElement = template.content.firstElementChild.cloneNode(true);

            cellElement.dataset.row = row.toString();
            cellElement.dataset.col = col.toString();

            cellElement.addEventListener('click', () => selectCell(row, col));
            cellElement.addEventListener('keydown', (event) => handleCellKey(event, row, col));

            boardElement.appendChild(cellElement);
        }
    }
}

function selectCell(row, col) {
    if (!currentSessionId) return;
    if (isEliminated) {
        updateStatus('You have reached the mistake limit and cannot make moves.', 'warn');
        return;
    }

    selectedCell = { row, col };

    if (currentPlayer) {
        activeSelections.set(currentPlayer.id, { row, col });
    }

    renderBoard();

    const cell = document.querySelector(`.cell[data-row="${row}"][data-col="${col}"]`);
    if (cell) {
        cell.focus();
    }

    announceSelection(row, col);
}

function handleCellKey(event, row, col) {
    if (!currentSessionId) return;
    if (isEliminated) {
        return;
    }

    const key = event.key;

    if (key === 'ArrowUp' && row > 0) {
        selectCell(row - 1, col);
    } else if (key === 'ArrowDown' && row < 8) {
        selectCell(row + 1, col);
    } else if (key === 'ArrowLeft' && col > 0) {
        selectCell(row, col - 1);
    } else if (key === 'ArrowRight' && col < 8) {
        selectCell(row, col + 1);
    } else if (/^[1-9]$/.test(key)) {
        submitMove(Number(key));
    } else if (key === '0' || key.toLowerCase() === 'backspace' || key.toLowerCase() === 'delete') {
        submitMove(0);
    }
}

async function submitMove(value) {
    if (!currentSessionId || !currentPlayer) {
        updateStatus('Join a session before playing.', 'warn');
        return;
    }

    if (isEliminated) {
        updateStatus('You have reached the mistake limit and cannot make moves.', 'error');
        return;
    }

    if (!selectedCell) {
        updateStatus('Select a cell first.', 'warn');
        return;
    }

    const { row, col } = selectedCell;

    try {
        const response = await fetch(`/api/session/${currentSessionId}/move`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playerId: currentPlayer.id, row, col, value })
        });

        const data = await response.json();

        if (!response.ok || data.success === false) {
            updateStatus(data.message || 'Move rejected.', 'error');
        } else {
            updateStatus(data.message || 'Move applied.', 'success');
        }

        if (data.state) {
            hydrateState(data);
        }
    } catch (error) {
        updateStatus('Failed to send move.', 'error');
        console.error(error);
    }
}

async function pollState() {
    if (!currentSessionId) return;
    if (isFetching) return;
    isFetching = true;

    try {
        const response = await fetch(`/api/session/${currentSessionId}/state`, {
            credentials: 'include' // Important for sending cookies
        });

        if (!response.ok) {
            if (response.status === 401) {
                handleSessionExpired();
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (!response.ok || data.success === false) {
            updateStatus(data.message || 'Failed to fetch state.', 'error');
            return;
        }

        hydrateState(data);
    } catch (error) {
        updateStatus('Failed to fetch game state.', 'error');
        console.error(error);
    } finally {
        isFetching = false;
    }
}

function hydrateState(payload) {
    let playersList = null;
    if (payload.session) {
        currentSessionId = payload.session.id;
        currentSessionDifficulty = payload.session.difficulty || currentSessionDifficulty;
        sessionIdDisplay.textContent = currentSessionId;
        sessionInfoSection.hidden = false;
        sessionStatus.textContent = `Session ${currentSessionId} • Difficulty: ${payload.session.difficulty}`;
        toggleLobbyState(true);
    }

    if (payload.player) {
        currentPlayer = payload.player;
        currentPlayer.isHost = Boolean(payload.player.isHost);
        playerColorCache.set(payload.player.id, payload.player.color);
        document.documentElement.style.setProperty('--player-highlight', currentPlayer.color);
        updateChatHeading();
    }

    if (payload.players) {
        playersList = payload.players;
        latestPlayersSnapshot = payload.players;
        updateChatHeading(playersList);
    }

    if (payload.state) {
        latestStateSnapshot = payload.state;
        mistakeLimit = payload.state.mistakeLimit ?? mistakeLimit;
        boardState = payload.state.board || [];
        givens = payload.state.givens || [];
        claims = payload.state.claims || [];

        activeSelections.clear();
        const selections = payload.state.selections || {};
        Object.entries(selections).forEach(([playerId, coords]) => {
            if (coords && Number.isInteger(coords.row) && Number.isInteger(coords.col)) {
                activeSelections.set(playerId, { row: coords.row, col: coords.col });
            }
        });

        if (currentPlayer) {
            const localSelection = activeSelections.get(currentPlayer.id);
            if (localSelection) {
                selectedCell = { ...localSelection };
            } else if (selectedCell) {
                activeSelections.set(currentPlayer.id, { ...selectedCell });
            }
            const key = localSelection ? selectionKey(localSelection.row, localSelection.col) : null;
            lastSentSelectionKey = key;
        }

        renderBoard();

        if (Array.isArray(payload.state.chatLog)) {
            syncChatLog(payload.state.chatLog);
        }

        if (payload.state.complete) {
            updateStatus('Puzzle solved! Great job everyone!', 'success');
        }
    }

    if (playersList || latestPlayersSnapshot.length) {
        const roster = playersList ?? latestPlayersSnapshot;
        renderScoreboard(roster, mistakeLimit);
        updatePlayerStatus(roster);
        updateRestartAvailability(roster);
    }

    updateOverlayVisibility();
    updateControlsAvailability();
    updateChatAvailability();

    const hasSession = Boolean(currentSessionId);
    boardEmptyMessage.hidden = hasSession;
    boardControls.hidden = !currentSessionId;
    startPolling();
}

async function refreshSession() {
    if (sessionRefreshDisabled) return;

    try {
        const response = await fetch('/api/v1/auth/refresh-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include', // Important for sending cookies
            body: JSON.stringify({}) // session id comes from the cookie
        });

        if (!response.ok) {
            // 400 = no session cookie at all, i.e. playing as a guest. Nothing
            // to keep alive, so stop pinging instead of logging every cycle.
            if (response.status === 400) {
                sessionRefreshDisabled = true;
                stopSessionRefresh();
                return;
            }

            const error = await response.json().catch(() => ({}));
            console.warn('Session refresh failed:', error);
            // If refresh fails, clear the session
            if (response.status === 401) {
                handleSessionExpired();
            }
        }
    } catch (error) {
        console.error('Error refreshing session:', error);
    }
}

function startSessionRefresh() {
    if (sessionRefreshDisabled) return;

    // Initial refresh
    refreshSession();
    
    // Set up periodic refresh
    if (!sessionRefreshInterval) {
        sessionRefreshInterval = setInterval(refreshSession, SESSION_REFRESH_INTERVAL);
    }
}

function stopSessionRefresh() {
    if (sessionRefreshInterval) {
        clearInterval(sessionRefreshInterval);
        sessionRefreshInterval = null;
    }
}

function handleSessionExpired() {
    stopPolling();
    stopSessionRefresh();
    
    // Show a message to the user
    updateStatus('Your session has expired. Please log in again.', 'error');
    
    // Redirect to login after a short delay
    setTimeout(() => {
        window.location.href = '/login';
    }, 3000);
}

function startPolling() {
    if (!pollingInterval) {
        pollingInterval = setInterval(pollState, POLLING_INTERVAL);
    }
    
    // Start session refresh when polling starts
    startSessionRefresh();
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
    stopSessionRefresh();
}

function handleJoin(event) {
    event.preventDefault();

    if (currentSessionId) {
        updateStatus('You are already in a session. Leave before joining another.', 'warn');
        return;
    }

    const name = joinNameInput.value.trim();
    const sessionId = joinSessionInput.value.trim().toUpperCase();

    if (!name || !sessionId) {
        updateStatus('Name and session ID required.', 'warn');
        return;
    }

    joinSession(name, sessionId);
}

async function joinSession(name, sessionId) {
    try {
        const response = await fetch(`/api/session/${sessionId}/join`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include', // Important for sending cookies
            body: JSON.stringify({ name }),
        });

        const data = await response.json();
        if (!response.ok || data.success === false) {
            updateStatus(data.message || 'Unable to join session.', 'error');
            return;
        }

        currentPlayer = data.player;
        currentSessionId = data.session.id;
        hydrateState(data);
        toggleLobbyState(true);
        updateStatus(`Joined session ${currentSessionId} as ${name}.`, 'success');
    } catch (error) {
        updateStatus('Join request failed.', 'error');
        console.error(error);
    }
}

function handleHost(event) {
    event.preventDefault();

    if (currentSessionId) {
        updateStatus('You are already hosting or joined a session.', 'warn');
        return;
    }

    const name = hostNameInput.value.trim();
    const difficulty = hostDifficultySelect.value;

    if (!name) {
        updateStatus('Host name is required.', 'warn');
        return;
    }

    createSession(name, difficulty);
}

async function createSession(name, difficulty) {
    try {
        const response = await fetch('/api/session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include', // Important for sending cookies
            body: JSON.stringify({
                name,
                difficulty,
            }),
        });

        const data = await response.json();
        if (!response.ok || data.success === false) {
            updateStatus(data.message || 'Unable to create session.', 'error');
            return;
        }

        currentPlayer = data.player;
        currentSessionId = data.session.id;
        hydrateState(data);
        toggleLobbyState(true);
        updateStatus(`Hosting session ${currentSessionId}. Share the ID!`, 'success');
    } catch (error) {
        updateStatus('Session creation failed.', 'error');
        console.error(error);
    }
}

function setupEventListeners() {
    window.addEventListener('focus', () => pollState());
    joinForm.addEventListener('submit', handleJoin);
    hostForm.addEventListener('submit', handleHost);
    leaveButton.addEventListener('click', leaveSession);
    if (chatForm) {
        chatForm.addEventListener('submit', handleChatSubmit);
    }
    if (emojiBar) {
        emojiBar.addEventListener('click', handleEmojiClick);
    }
    if (restartButton) {
        restartButton.addEventListener('click', handleRestartClick);
    }
}

function init() {
    createNumberButtons();
    initBoard();
    setupEventListeners();
}

window.addEventListener('DOMContentLoaded', init);

/* ---------------------------------------------------------------------------
 * Rendering / status helpers
 * ------------------------------------------------------------------------- */

function updateStatus(message, state = 'info') {
    if (!statusBar) return;
    statusBar.textContent = message;
    statusBar.dataset.state = state;
}

function isCurrentPlayerHost() {
    if (!currentPlayer) return false;
    const match = latestPlayersSnapshot.find((player) => player.id === currentPlayer.id);
    return Boolean(match ? match.isHost : currentPlayer.isHost);
}

function cachePlayerColors(roster = []) {
    roster.forEach((player) => {
        if (player?.id && player.color) {
            playerColorCache.set(player.id, player.color);
        }
    });
}

function renderBoard() {
    if (!boardElement) return;

    const cells = boardElement.querySelectorAll('.cell');
    if (!cells.length) return;

    // Map cell -> list of player ids currently pointing at it.
    const selectionsByCell = new Map();
    activeSelections.forEach((coords, playerId) => {
        if (!coords) return;
        const key = selectionKey(coords.row, coords.col);
        if (!selectionsByCell.has(key)) {
            selectionsByCell.set(key, []);
        }
        selectionsByCell.get(key).push(playerId);
    });

    cells.forEach((cell) => {
        const row = Number(cell.dataset.row);
        const col = Number(cell.dataset.col);
        const valueDisplay = cell.querySelector('.cell-value');

        const value = boardState?.[row]?.[col] ?? 0;
        const isGiven = Boolean(givens?.[row]?.[col]);
        const claimedBy = claims?.[row]?.[col] || null;

        valueDisplay.textContent = value ? String(value) : '';

        cell.dataset.given = isGiven ? 'true' : 'false';
        cell.dataset.editable = !isGiven && !isEliminated ? 'true' : 'false';
        cell.dataset.claimed = claimedBy ? 'true' : 'false';
        cell.disabled = isEliminated;

        // Colour cells by the player who filled them.
        if (claimedBy) {
            const claimColor = playerColorCache.get(claimedBy) || '#f2a900';
            cell.style.setProperty('--cell-claim-color', withAlpha(claimColor, 0.22));
            cell.style.setProperty('--cell-claim-border', withAlpha(claimColor, 0.65));
            valueDisplay.style.color = claimColor;
        } else {
            cell.style.removeProperty('--cell-claim-color');
            cell.style.removeProperty('--cell-claim-border');
            valueDisplay.style.color = isGiven ? '#fafafa' : '#fefefe';
        }

        // Highlight selections (mine strongest, other players softer).
        const key = selectionKey(row, col);
        const watchers = selectionsByCell.get(key) || [];
        const mine = Boolean(currentPlayer && watchers.includes(currentPlayer.id));
        const others = watchers.filter((playerId) => playerId !== currentPlayer?.id);

        cell.dataset.selected = mine ? 'true' : 'false';
        cell.setAttribute('aria-selected', mine ? 'true' : 'false');

        if (mine) {
            const myColor = getActivePlayerColor();
            cell.style.setProperty('--cell-selection-color', withAlpha(myColor, 0.45));
        } else if (others.length) {
            const otherColor = playerColorCache.get(others[0]) || '#45aaf2';
            cell.style.setProperty('--cell-selection-color', withAlpha(otherColor, 0.2));
        } else {
            cell.style.removeProperty('--cell-selection-color');
        }
    });
}

function renderScoreboard(roster = [], limit = mistakeLimit) {
    if (!scoreList) return;

    cachePlayerColors(roster);
    scoreboardSection.hidden = roster.length === 0;
    scoreList.innerHTML = '';

    roster.forEach((player) => {
        const item = document.createElement('li');
        item.className = 'score-item';
        item.dataset.eliminated = player.eliminated ? 'true' : 'false';

        const swatch = document.createElement('span');
        swatch.className = 'score-color';
        swatch.style.background = player.color || '#f2a900';

        const name = document.createElement('span');
        name.className = 'score-name';
        if (player.isHost) {
            name.classList.add('score-host');
        }
        name.textContent = player.name;

        const score = document.createElement('span');
        score.className = 'score-value';
        score.textContent = `${player.score ?? 0} pts`;

        const mistakes = document.createElement('span');
        mistakes.className = 'score-mistakes';
        mistakes.dataset.state = player.eliminated ? 'eliminated' : 'active';
        mistakes.textContent = `${player.mistakes ?? 0}/${limit}`;

        item.append(swatch, name, score, mistakes);
        scoreList.appendChild(item);
    });
}

function updatePlayerStatus(roster = []) {
    cachePlayerColors(roster);

    if (!currentPlayer) {
        isEliminated = false;
        updateMistakeDisplay(0);
        return;
    }

    const me = roster.find((player) => player.id === currentPlayer.id);
    if (me) {
        currentPlayer = { ...currentPlayer, ...me };
        playerColorCache.set(me.id, me.color);
        document.documentElement.style.setProperty('--player-highlight', me.color);
    }

    isEliminated = Boolean(me?.eliminated);
    updateMistakeDisplay(me?.mistakes ?? 0);

    if (lossBanner) {
        lossBanner.hidden = !isEliminated;
    }
}

function updateRestartAvailability(roster = []) {
    if (!restartContainer) return;

    const puzzleComplete = Boolean(latestStateSnapshot?.complete);
    const everyoneOut = roster.length > 0 && roster.every((player) => player.eliminated);
    const showRestart = Boolean(currentSessionId) && everyoneOut && !puzzleComplete;

    restartContainer.hidden = !showRestart;
    restartContainer.classList.toggle('d-none', !showRestart);

    if (!restartButton) return;

    const hosting = isCurrentPlayerHost();
    restartButton.disabled = !showRestart || !hosting;

    const message = restartContainer.querySelector('.restart-message');
    if (message) {
        message.textContent = hosting
            ? 'Everyone is out! As host, you can restart the puzzle for the same lobby.'
            : 'Everyone is out! Waiting for the host to restart the puzzle.';
    }
}

function formatChatTimestamp(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function syncChatLog(entries = []) {
    if (!chatLogElement) return;

    const latestId = entries.length ? entries[entries.length - 1].id : null;
    if (latestId === lastChatId && chatLogElement.childElementCount === entries.length) {
        return;
    }

    chatLog = entries;
    lastChatId = latestId;
    chatLogElement.innerHTML = '';

    entries.forEach((entry) => {
        const wrapper = document.createElement('article');
        wrapper.className = 'chat-message';
        wrapper.dataset.playerId = entry.playerId || '';

        const author = document.createElement('span');
        author.className = 'chat-author';
        author.style.color = entry.color || playerColorCache.get(entry.playerId) || '#f2a900';
        author.textContent = entry.playerName || 'Player';

        const text = document.createElement('span');
        text.className = 'chat-text';
        text.textContent = entry.message;

        const time = document.createElement('span');
        time.className = 'chat-timestamp';
        time.textContent = formatChatTimestamp(entry.timestamp);

        wrapper.append(author, text, time);
        chatLogElement.appendChild(wrapper);
    });

    chatLogElement.scrollTop = chatLogElement.scrollHeight;
}

/* ---------------------------------------------------------------------------
 * Lobby / chat actions
 * ------------------------------------------------------------------------- */

async function leaveSession() {
    if (!currentSessionId || !currentPlayer) {
        resetClientState();
        return;
    }

    const sessionId = currentSessionId;
    const playerId = currentPlayer.id;

    try {
        const response = await fetch(`/api/session/${sessionId}/leave`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ playerId }),
        });

        const data = await response.json().catch(() => ({}));
        resetClientState();

        if (!response.ok || data.success === false) {
            updateStatus(data.detail || data.message || 'Unable to leave the session.', 'error');
            return;
        }

        updateStatus(data.message || 'You have left the game.', 'info');
    } catch (error) {
        resetClientState();
        updateStatus('Leave request failed.', 'error');
        console.error(error);
    }
}

async function sendChatMessage(message) {
    const content = (message || '').trim();
    if (!content) return;

    if (!currentSessionId || !currentPlayer) {
        updateStatus('Join a session before chatting.', 'warn');
        return;
    }

    try {
        const response = await fetch(`/api/session/${currentSessionId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ playerId: currentPlayer.id, message: content }),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            updateStatus(data.detail || data.message || 'Unable to send message.', 'error');
            return;
        }

        if (data.state?.chatLog) {
            syncChatLog(data.state.chatLog);
        }
        if (data.players) {
            latestPlayersSnapshot = data.players;
            renderScoreboard(data.players, mistakeLimit);
        }
    } catch (error) {
        updateStatus('Failed to send message.', 'error');
        console.error(error);
    }
}

function handleChatSubmit(event) {
    event.preventDefault();
    if (!chatInput) return;
    const message = chatInput.value;
    chatInput.value = '';
    sendChatMessage(message);
}

function handleEmojiClick(event) {
    const button = event.target.closest('.emoji-btn');
    if (!button || button.disabled) return;
    sendChatMessage(button.dataset.emoji || '');
}

async function handleRestartClick() {
    if (!currentSessionId || !currentPlayer) {
        updateStatus('Join a session before restarting.', 'warn');
        return;
    }

    if (!isCurrentPlayerHost()) {
        updateStatus('Only the host can restart the puzzle.', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/session/${currentSessionId}/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playerId: currentPlayer.id,
                difficulty: currentSessionDifficulty,
            }),
        });

        const data = await response.json();
        if (!response.ok || data.success === false) {
            updateStatus(data.message || 'Unable to restart the puzzle.', 'error');
            return;
        }

        updateStatus('Puzzle restarted for the lobby.', 'success');
        hydrateState(data);
    } catch (error) {
        updateStatus('Failed to restart the puzzle.', 'error');
        console.error(error);
    }
}

