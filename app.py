from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
import time
import uuid
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SESSION_TYPE'] = 'filesystem'
socketio = SocketIO(app, async_mode='threading')  # Use threading, compatible with Gunicorn
from flask_session import Session
Session(app)

# Global variables to store game state
players = []
game_started = False
winners = []
countdown_start_time = None
countdown_duration = 10
countdown_active = False
game_id = str(uuid.uuid4())
last_activity_time = time.time()

def get_middle_players(players):
    print(f"Calculating middle players for: {players}")
    if len(players) < 3:
        return []
    unique_guesses = sorted(set(p['guess'] for p in players))
    print(f"Unique guesses: {unique_guesses}")
    if len(unique_guesses) < 3:
        return []
    if len(unique_guesses) % 2 == 0:
        return []
    middle_guess = unique_guesses[len(unique_guesses) // 2]
    print(f"Middle guess: {middle_guess}")
    result = [p for p in players if p['guess'] == middle_guess]
    print(f"Winners: {result}")
    return result

def broadcast_game_state():
    global last_activity_time
    last_activity_time = time.time()
    print(f"Broadcasting game state: players={len(players)}, game_started={game_started}, winners={winners}")
    socketio.emit('update_game_state', {
        'players': players,
        'game_started': game_started,
        'winners': winners
    }, namespace='/')

@app.route('/', methods=['GET', 'POST'])
def index():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    if 'game_id' not in session or session['game_id'] != game_id:
        session['game_id'] = game_id
        session['submitted'] = False
    if request.method == 'POST' and not game_started:
        name = request.form.get('name')
        guess = request.form.get('guess')
        if name and guess:
            try:
                guess = int(guess)
                if not (1 <= guess <= 100):
                    return render_template('index.html', players=players, game_started=game_started,
                                          winners=winners, countdown_active=countdown_active,
                                          error="Guess must be between 1 and 100!")
                if any(player['name'] == name for player in players):
                    return render_template('index.html', players=players, game_started=game_started,
                                          winners=winners, countdown_active=countdown_active,
                                          error="Name already taken!")
                players.append({'name': name, 'guess': guess})
                session['submitted'] = True
                broadcast_game_state()
                if len(players) >= 3 and not countdown_active:
                    countdown_active = True
                    countdown_start_time = time.time()
                    socketio.start_background_task(countdown)
                elif len(players) > 3 and countdown_active:
                    countdown_start_time = time.time()
            except ValueError:
                return render_template('index.html', players=players, game_started=game_started,
                                      winners=winners, countdown_active=countdown_active,
                                      error="Guess must be a valid number!")
        else:
            return render_template('index.html', players=players, game_started=game_started,
                                  winners=winners, countdown_active=countdown_active,
                                  error="Please provide both name and guess!")
    return render_template('index.html', players=players, game_started=game_started,
                          winners=winners, countdown_active=countdown_active)

@app.route('/result')
def result():
    global players, winners, game_started
    print(f"Rendering result page: players={len(players)}, winners={winners}")
    return render_template('result.html', players=players, winners=winners, game_started=game_started)

@socketio.on('connect', namespace='/')
def handle_connect():
    print('Client connected')
    emit('update_game_state', {
        'players': players,
        'game_started': game_started,
        'winners': winners
    })
    if countdown_active and countdown_start_time is not None:
        remaining_time = max(0, countdown_duration - (time.time() - countdown_start_time))
        emit('update_countdown', {
            'countdown_active': countdown_active and remaining_time > 0,
            'remaining_time': remaining_time
        })

@app.route('/reset', methods=['POST'])
def reset():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    print('Resetting game')
    players = []
    game_started = False
    winners = []
    countdown_start_time = None
    countdown_active = False
    game_id = str(uuid.uuid4())
    session.clear()
    session['game_id'] = game_id
    session['submitted'] = False
    last_activity_time = time.time()
    socketio.emit('game_reset', {}, namespace='/')  # Notify all clients to clear sessions
    broadcast_game_state()  # Sync state with all clients
    return redirect(url_for('index'))

def countdown():
    global countdown_active, game_started, winners, countdown_start_time, last_activity_time
    while countdown_active and countdown_start_time is not None:
        elapsed_time = time.time() - countdown_start_time
        remaining_time = max(0, countdown_duration - elapsed_time)
        socketio.emit('update_countdown', {
            'countdown_active': countdown_active and remaining_time > 0,
            'remaining_time': remaining_time
        }, namespace='/')
        if remaining_time <= 0:
            countdown_active = False
            game_started = True
            winners = get_middle_players(players)
            broadcast_game_state()  # Update winners to all clients
            socketio.emit('redirect_to_result', {}, namespace='/')
            socketio.start_background_task(auto_reset)  # Start auto-reset check
            break
        socketio.sleep(0.1)

def auto_reset():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    while True:
        inactive_time = time.time() - last_activity_time
        if not countdown_active and not game_started and len(players) < 3 and inactive_time >= 10:
            print('Auto-resetting due to inactivity')
            players = []
            game_started = False
            winners = []
            countdown_start_time = None
            countdown_active = False
            game_id = str(uuid.uuid4())
            socketio.emit('game_reset', {}, namespace='/')
            broadcast_game_state()
            break
        socketio.sleep(1)

@socketio.on('game_reset')
def handle_game_reset():
    session.clear()
    session['game_id'] = request.sid  # Unique per client
    session['submitted'] = False

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
