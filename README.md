# Numbers Game

A multiplayer web game built with Flask and Flask-SocketIO where players guess a number between 1 and 100, aiming for the middle value among all guesses. The game uses WebSockets for real-time updates, allowing players to join, see live countdowns, and view results instantly.

## Features
- Real-time multiplayer gameplay with WebSocket support.
- Players enter a name and a guess (1–100).
- Game starts with 3 or more players after a 10-second countdown.
- The player(s) who guess the middle number win; ties are handled as draws.
- Session management to prevent multiple guesses per player.

## Setup (Local Development)
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/numbers-game.git
   cd numbers-game